import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { refreshOnce } from '@/shared/lib/api/client'
import { type SocketEvent, type SocketState, socketUrl, WsClient } from '@/shared/lib/ws/ws-client'

import { fromServer, type MessageOut, useMessageStore } from './message-store'
import { channelKeys } from './queries'

export interface ChannelSocket {
  state: SocketState
  /** Ids of members with at least one open connection to this channel. */
  online: ReadonlySet<string>
}

/** Keeps a WebSocket to the channel open while the room is shown. */
export function useChannelSocket(channelId: string, enabled: boolean): ChannelSocket {
  const queryClient = useQueryClient()
  const [state, setState] = useState<SocketState>('closed')
  const [online, setOnline] = useState<ReadonlySet<string>>(new Set())

  useEffect(() => {
    if (!enabled) return
    const handle = (event: SocketEvent) => {
      switch (event.type) {
        case 'presence.snapshot':
          setOnline(new Set(event.data.online_user_ids as string[]))
          break
        case 'presence.update': {
          const { user_id: userId, online: isOnline } = event.data as { user_id: string; online: boolean }
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
        // processing and failed come over the user's own topic, shared by all of their rooms.
        case 'message.ready':
        case 'message.processing': {
          const message = event.data as unknown as MessageOut
          if (message.channel_id === channelId) useMessageStore.getState().upsert([fromServer(message)])
          break
        }
        case 'message.failed': {
          const failed = event.data as { channel_id: string; client_msg_id: string; reason: string }
          if (failed.channel_id === channelId) useMessageStore.getState().markFailed(channelId, failed.client_msg_id, failed.reason)
          break
        }
      }
    }
    const client = new WsClient({
      url: socketUrl(`/ws/channels/${channelId}`),
      onEvent: handle,
      refreshSession: refreshOnce,
      onStateChange: (next) => {
        setState(next)
        // Anything may have changed while disconnected.
        if (next === 'open') void queryClient.invalidateQueries({ queryKey: channelKeys.members(channelId) })
      },
    })
    client.connect()
    return () => client.close()
  }, [channelId, enabled, queryClient])

  return { state, online }
}
