import { create } from 'zustand'

import type { components } from '@/shared/lib/api/schema'

export type MessageOut = components['schemas']['MessageOut']
export type ReceiptSummary = components['schemas']['ReceiptSummary']

export interface Transcript {
  status: 'pending' | 'done' | 'failed'
  text: string | null
  /** Language code the speech was recognised in, e.g. "en". */
  lang: string | null
}

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
  /** Delivered/played counts, on the user's own ready messages. */
  receipts: ReceiptSummary | null
  /** Null when the server does not transcribe (transcription off, or older messages). */
  transcript: Transcript | null
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
    receipts: message.receipts ?? null,
    transcript: message.transcript_status
      ? { status: message.transcript_status, text: message.transcript ?? null, lang: message.transcript_lang ?? null }
      : null,
  }
}

/** A finished transcript is never replaced by an older copy that still says pending. */
function newerTranscript(existing: Transcript | null | undefined, incoming: Transcript | null): Transcript | null {
  if (existing && existing.status !== 'pending' && incoming?.status === 'pending') return existing
  return incoming ?? existing ?? null
}

type ChannelMessages = Record<string, ChatMessage>

interface MessageState {
  byChannel: Record<string, ChannelMessages>
  /** Adds or replaces a message the browser is uploading (also used for retries). */
  putLocal: (message: ChatMessage) => void
  /** Merges server copies; never moves a message back to an earlier status. */
  upsert: (messages: ChatMessage[]) => void
  markFailed: (channelId: string, clientMsgId: string, reason: string) => void
  setReceipts: (channelId: string, messageId: string, receipts: ReceiptSummary) => void
  setTranscript: (channelId: string, messageId: string, transcript: Transcript) => void
  remove: (channelId: string, clientMsgId: string) => void
}

/** Applies `changes` to the message with server id `messageId`, if the browser has it. */
function updateById(
  state: MessageState,
  channelId: string,
  messageId: string,
  changes: Partial<ChatMessage>,
): Partial<MessageState> | MessageState {
  const channel = state.byChannel[channelId]
  const message = Object.values(channel ?? {}).find((candidate) => candidate.id === messageId)
  if (!channel || !message) return state
  return { byChannel: { ...state.byChannel, [channelId]: { ...channel, [message.clientMsgId]: { ...message, ...changes } } } }
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
        // The server now has the recording; the local copy is no longer needed. Live receipt
        // counts are newer than the ones a message event carries.
        channel[incoming.clientMsgId] = {
          ...incoming,
          receipts: existing?.receipts ?? incoming.receipts,
          transcript: newerTranscript(existing?.transcript, incoming.transcript),
          upload: incoming.id ? undefined : existing?.upload,
        }
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
  setReceipts: (channelId, messageId, receipts) => set((state) => updateById(state, channelId, messageId, { receipts })),
  setTranscript: (channelId, messageId, transcript) =>
    set((state) => updateById(state, channelId, messageId, { transcript })),
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

/** Highest seq the browser has for a channel, or null before any ready message. */
export function lastSeq(channelId: string): number | null {
  const seqs = Object.values(useMessageStore.getState().byChannel[channelId] ?? {})
    .filter((message) => message.status === 'ready' && message.seq !== null)
    .map((message) => message.seq as number)
  return seqs.length ? Math.max(...seqs) : null
}

/** Lowest seq loaded, for paging back through history. */
export function firstSeq(channelId: string): number | null {
  const seqs = Object.values(useMessageStore.getState().byChannel[channelId] ?? {})
    .filter((message) => message.seq !== null)
    .map((message) => message.seq as number)
  return seqs.length ? Math.min(...seqs) : null
}
