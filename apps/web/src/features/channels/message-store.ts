import { create } from 'zustand'

import type { components } from '@/shared/lib/api/schema'

export type MessageOut = components['schemas']['MessageOut']

/** uploading: not on the server yet; processing/ready/failed: the server's status. */
export type MessageStatus = 'uploading' | 'processing' | 'ready' | 'failed'

export interface ChatMessage {
  /** Created by the browser; links the optimistic bubble, the upload and every server event. */
  clientMsgId: string
  id: string | null
  channelId: string
  sender: { id: string; username: string }
  status: MessageStatus
  seq: number | null
  durationMs: number | null
  waveform: number[] | null
  failureReason: string | null
  createdAt: string
  /** Kept until the server has the recording, so a failed upload can be retried. */
  upload?: Blob
}

// Events can arrive in any order (ready before the upload's 202): status only moves forward.
const RANK: Record<MessageStatus, number> = { uploading: 0, processing: 1, failed: 2, ready: 3 }

export function fromServer(message: MessageOut): ChatMessage {
  return {
    clientMsgId: message.client_msg_id,
    id: message.id,
    channelId: message.channel_id,
    sender: message.sender,
    status: message.status,
    seq: message.seq,
    durationMs: message.duration_ms,
    waveform: message.waveform,
    failureReason: message.failure_reason,
    createdAt: message.created_at,
  }
}

type ChannelMessages = Record<string, ChatMessage>

interface MessageState {
  byChannel: Record<string, ChannelMessages>
  /** Adds or replaces a message the browser is uploading (also used for retries). */
  putLocal: (message: ChatMessage) => void
  /** Merges server copies; never moves a message back to an earlier status. */
  upsert: (messages: ChatMessage[]) => void
  markFailed: (channelId: string, clientMsgId: string, reason: string) => void
  remove: (channelId: string, clientMsgId: string) => void
}

export const useMessageStore = create<MessageState>()((set) => ({
  byChannel: {},
  putLocal: (message) =>
    set((state) => ({
      byChannel: {
        ...state.byChannel,
        [message.channelId]: { ...state.byChannel[message.channelId], [message.clientMsgId]: message },
      },
    })),
  upsert: (messages) =>
    set((state) => {
      const byChannel = { ...state.byChannel }
      for (const incoming of messages) {
        const channel = { ...byChannel[incoming.channelId] }
        const existing = channel[incoming.clientMsgId]
        if (existing && RANK[incoming.status] < RANK[existing.status]) continue
        // The server now has the recording; the local copy is no longer needed.
        channel[incoming.clientMsgId] = { ...incoming, upload: incoming.id ? undefined : existing?.upload }
        byChannel[incoming.channelId] = channel
      }
      return { byChannel }
    }),
  markFailed: (channelId, clientMsgId, reason) =>
    set((state) => {
      const existing = state.byChannel[channelId]?.[clientMsgId]
      if (!existing || existing.status === 'ready') return state
      return {
        byChannel: {
          ...state.byChannel,
          [channelId]: { ...state.byChannel[channelId], [clientMsgId]: { ...existing, status: 'failed', failureReason: reason } },
        },
      }
    }),
  remove: (channelId, clientMsgId) =>
    set((state) => {
      const channel = { ...state.byChannel[channelId] }
      delete channel[clientMsgId]
      return { byChannel: { ...state.byChannel, [channelId]: channel } }
    }),
}))

/** Ready messages in seq order, then the user's own messages that are not ready yet. */
export function orderMessages(messages: ChannelMessages | undefined): ChatMessage[] {
  const all = Object.values(messages ?? {})
  const ready = all.filter((message) => message.status === 'ready').sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0))
  const pending = all.filter((message) => message.status !== 'ready').sort((a, b) => a.createdAt.localeCompare(b.createdAt))
  return [...ready, ...pending]
}
