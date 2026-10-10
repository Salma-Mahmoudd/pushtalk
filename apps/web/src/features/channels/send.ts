import { ApiError, apiRequest } from '@/shared/lib/api/client'

import { type ChatMessage, fromServer, type MessageOut, useMessageStore } from './message-store'

const EXTENSIONS: Record<string, string> = { 'audio/webm': '.webm', 'audio/ogg': '.ogg', 'audio/mp4': '.m4a' }

function failureText(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Not sent. Check the connection.'
  if (error.code === 'rate_limited') return `Slow down. Try again in ${error.retryAfter ?? 60} s.`
  if (error.code === 'network_error') return 'Not sent. Check the connection.'
  return error.message
}

/**
 * Uploads a recording. A retry of an upload the server never accepted reuses its id, so a
 * request that did arrive (lost response) is not stored twice; a message the server already
 * rejected is sent again under a new id.
 */
export async function sendRecording(
  channelId: string,
  blob: Blob,
  sender: { id: string; username: string },
  retryOf?: ChatMessage,
): Promise<void> {
  const store = useMessageStore.getState()
  const reuseId = retryOf !== undefined && retryOf.id === null
  if (retryOf && !reuseId) store.remove(channelId, retryOf.clientMsgId)
  const clientMsgId = reuseId ? retryOf.clientMsgId : crypto.randomUUID()

  store.putLocal({
    clientMsgId,
    id: null,
    channelId,
    sender,
    status: 'uploading',
    seq: null,
    durationMs: null,
    waveform: null,
    failureReason: null,
    createdAt: retryOf?.createdAt ?? new Date().toISOString(),
    receipts: null,
    upload: blob,
  })

  const form = new FormData()
  form.append('client_msg_id', clientMsgId)
  form.append('file', blob, `recording${EXTENSIONS[blob.type.split(';')[0]] ?? ''}`)
  try {
    const message = await apiRequest<MessageOut>(`/api/channels/${channelId}/messages`, { method: 'POST', body: form })
    useMessageStore.getState().upsert([fromServer(message)])
  } catch (error) {
    useMessageStore.getState().markFailed(channelId, clientMsgId, failureText(error))
  }
}
