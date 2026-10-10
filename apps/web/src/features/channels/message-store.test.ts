import { beforeEach, describe, expect, it } from 'vitest'

import { type ChatMessage, orderMessages, useMessageStore } from './message-store'

const SENDER = { id: 'u1', username: 'alice' }

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    clientMsgId: 'c1',
    id: 'm1',
    channelId: 'ch',
    sender: SENDER,
    status: 'processing',
    seq: null,
    durationMs: null,
    waveform: null,
    failureReason: null,
    createdAt: '2026-01-01T00:00:00Z',
    receipts: null,
    ...overrides,
  }
}

const channel = () => useMessageStore.getState().byChannel.ch

describe('message store', () => {
  beforeEach(() => useMessageStore.setState({ byChannel: {} }))

  it('never moves a message back to an earlier status', () => {
    const { upsert } = useMessageStore.getState()
    upsert([message({ status: 'ready', seq: 1 })]) // WebSocket event first…
    upsert([message({ status: 'processing' })]) // …then the upload's 202 response

    expect(channel().c1.status).toBe('ready')
    expect(channel().c1.seq).toBe(1)
  })

  it('drops the local recording once the server has it', () => {
    const blob = new Blob(['audio'])
    useMessageStore.getState().putLocal(message({ id: null, status: 'uploading', upload: blob }))
    useMessageStore.getState().upsert([message({ status: 'processing' })])

    expect(channel().c1.upload).toBeUndefined()
  })

  it('does not mark a ready message as failed', () => {
    useMessageStore.getState().upsert([message({ status: 'ready', seq: 3 })])
    useMessageStore.getState().markFailed('ch', 'c1', 'late failure')

    expect(channel().c1.status).toBe('ready')
  })

  it('orders ready messages by seq, then pending ones by creation time', () => {
    const ordered = orderMessages({
      a: message({ clientMsgId: 'a', status: 'ready', seq: 2 }),
      b: message({ clientMsgId: 'b', status: 'uploading', createdAt: '2026-01-01T00:00:09Z' }),
      c: message({ clientMsgId: 'c', status: 'ready', seq: 1 }),
      d: message({ clientMsgId: 'd', status: 'failed', createdAt: '2026-01-01T00:00:05Z' }),
    })

    expect(ordered.map((item) => item.clientMsgId)).toEqual(['c', 'a', 'd', 'b'])
  })
})
