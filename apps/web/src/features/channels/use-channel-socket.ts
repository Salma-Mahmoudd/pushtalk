import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { apiRequest, refreshOnce } from '@/shared/lib/api/client'
import type { components } from '@/shared/lib/api/schema'
import { type SocketEvent, type SocketState, socketUrl, WsClient } from '@/shared/lib/ws/ws-client'

import { fromServer, lastSeq, type MessageOut, type ReceiptSummary, type Transcript, useMessageStore } from './message-store'
import { channelKeys } from './queries'

/** How long an unfocused tab waits before asking to play when nobody does. */
const CLAIM_IF_FREE_DELAY_MS = 1000

type MessagePage = components['schemas']['MessagePage']

export interface IncomingOptions {
  /** True for messages heard live or missed during a dropped connection. */
  autoplay: boolean
}

interface SocketHandlers {
  /** Ready messages from the socket (live, catch-up or gap fill), in seq order. */
  onIncoming: (messages: MessageOut[], options: IncomingOptions) => void
  /** Whether this tab is the one that plays the channel's audio. */
  onPlaybackActive: (active: boolean) => void
}

export interface ChannelSocket {
  state: SocketState
  /** Ids of members with at least one open connection to this channel. */
  online: ReadonlySet<string>
  /** Sends a client event; false when not connected. */
  send: (event: { type: string; data?: Record<string, unknown> }) => boolean
  /** Makes this tab the player ("play here"). */
  claimPlayback: () => void
}

/** Keeps a WebSocket to the channel open while the room is shown. */
export function useChannelSocket(channelId: string, enabled: boolean, handlers: SocketHandlers): ChannelSocket {
  const queryClient = useQueryClient()
  const [state, setState] = useState<SocketState>('closed')
  const [online, setOnline] = useState<ReadonlySet<string>>(new Set())
  const client = useRef<WsClient | null>(null)
  const handlersRef = useRef(handlers)

  useEffect(() => {
    handlersRef.current = handlers
  }, [handlers])

  useEffect(() => {
    if (!enabled) return
    let connectionId: string | null = null
    let opens = 0
    const store = () => useMessageStore.getState()
    const claim = () => socket.send({ type: 'playback.claim' })

    const receive = async (messages: MessageOut[], autoplay: boolean) => {
      const known = lastSeq(channelId)
      const first = messages[0]?.seq ?? null
      // A skipped number means a missed event: fetch the gap before going on.
      if (known !== null && first !== null && first > known + 1) {
        const page = await apiRequest<MessagePage>(`/api/channels/${channelId}/messages?after_seq=${known}&limit=200`).catch(
          () => null,
        )
        if (page) messages = [...page.messages.filter((message) => (message.seq ?? 0) < first), ...messages]
      }
      store().upsert(messages.map(fromServer))
      handlersRef.current.onIncoming(messages, { autoplay })
    }

    const handle = (event: SocketEvent) => {
      const data = event.data
      switch (event.type) {
        case 'hello':
          connectionId = data.connection_id as string
          break
        case 'presence.snapshot':
          setOnline(new Set(data.online_user_ids as string[]))
          break
        case 'presence.update': {
          const { user_id: userId, online: isOnline } = data as { user_id: string; online: boolean }
          setOnline((current) => {
            const next = new Set(current)
            if (isOnline) next.add(userId)
            else next.delete(userId)
            return next
          })
          break
        }
        case 'member.joined':
          void queryClient.invalidateQueries({ queryKey: channelKeys.members(channelId) })
          break
        case 'catchup':
          // Missed while disconnected: heard like live messages, but not on first opening.
          void receive(data.messages as MessageOut[], opens > 1)
          break
        case 'message.ready': {
          const message = data as unknown as MessageOut
          if (message.channel_id === channelId) void receive([message], true)
          break
        }
        case 'message.transcribed': {
          const done = data as {
            id: string
            channel_id: string
            transcript_status: Transcript['status']
            transcript: string | null
            transcript_lang: string | null
          }
          if (done.channel_id !== channelId) break
          store().setTranscript(channelId, done.id, {
            status: done.transcript_status,
            text: done.transcript,
            lang: done.transcript_lang,
          })
          break
        }
        // processing, failed, receipts and playback come over the user's own topic,
        // which every room of the user receives.
        case 'message.processing': {
          const message = data as unknown as MessageOut
          if (message.channel_id === channelId) store().upsert([fromServer(message)])
          break
        }
        case 'message.failed': {
          const failed = data as { channel_id: string; client_msg_id: string; reason: string }
          if (failed.channel_id === channelId) store().markFailed(channelId, failed.client_msg_id, failed.reason)
          break
        }
        case 'receipt.updated': {
          const receipt = data as unknown as ReceiptSummary & { message_id: string; channel_id: string }
          if (receipt.channel_id !== channelId) break
          store().setReceipts(channelId, receipt.message_id, {
            delivered: receipt.delivered,
            played: receipt.played,
            total: receipt.total,
          })
          void queryClient.invalidateQueries({ queryKey: ['receipts', receipt.message_id] })
          break
        }
        case 'playback.claimed': {
          const claimed = data as { channel_id: string; connection_id: string | null }
          if (claimed.channel_id !== channelId) break
          // Nobody plays (the playing tab closed): the focused tab takes over at once; otherwise
          // every other tab asks a moment later and the server lets only the first one play.
          if (claimed.connection_id === null) {
            if (document.hasFocus()) claim()
            else window.setTimeout(() => socket.send({ type: 'playback.claim_if_free' }), CLAIM_IF_FREE_DELAY_MS)
          }
          handlersRef.current.onPlaybackActive(claimed.connection_id !== null && claimed.connection_id === connectionId)
          break
        }
      }
    }

    const socket = new WsClient({
      url: () => {
        const known = lastSeq(channelId)
        return socketUrl(`/ws/channels/${channelId}${known === null ? '' : `?since_seq=${known}`}`)
      },
      onEvent: handle,
      refreshSession: refreshOnce,
      onStateChange: (next) => {
        setState(next)
        // A disconnected tab may already have lost playback to another one: it stays silent
        // until the server says who plays (on reconnect), so audio never plays twice.
        if (next === 'reconnecting') handlersRef.current.onPlaybackActive(false)
        if (next !== 'open') return
        opens += 1
        // Anything may have changed while disconnected; a focused tab is the one listening.
        void queryClient.invalidateQueries({ queryKey: channelKeys.members(channelId) })
        if (document.hasFocus()) claim()
      },
    })
    client.current = socket
    // The tab used most recently plays (DECISIONS.md, 1.4).
    window.addEventListener('focus', claim)
    socket.connect()
    return () => {
      window.removeEventListener('focus', claim)
      socket.close()
      client.current = null
    }
  }, [channelId, enabled, queryClient])

  const send = useCallback((event: { type: string; data?: Record<string, unknown> }) => client.current?.send(event) ?? false, [])
  const claimPlayback = useCallback(() => void client.current?.send({ type: 'playback.claim' }), [])

  return { state, online, send, claimPlayback }
}
