import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CLOSE_FORBIDDEN, CLOSE_UNAUTHORIZED, type SocketState, WsClient } from './ws-client'

class FakeSocket {
  static readonly OPEN = 1
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((message: { data: string }) => void) | null = null
  onclose: ((close: { code: number }) => void) | null = null

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
  }

  // Test controls
  serverOpens() {
    this.readyState = FakeSocket.OPEN
    this.onopen?.()
  }

  serverSends(event: unknown) {
    this.onmessage?.({ data: JSON.stringify(event) })
  }

  serverCloses(code: number) {
    this.readyState = 3
    this.onclose?.({ code })
  }
}

describe('WsClient', () => {
  let sockets: FakeSocket[]
  let states: SocketState[]
  let network: EventTarget
  const refreshSession = vi.fn<() => Promise<boolean>>()
  const onForbidden = vi.fn()
  const onEvent = vi.fn()

  function connect(): WsClient {
    const client = new WsClient({
      url: () => 'ws://test/ws/channels/1',
      onEvent,
      onStateChange: (state) => states.push(state),
      refreshSession,
      onForbidden,
      createSocket: () => {
        const socket = new FakeSocket()
        sockets.push(socket)
        return socket as unknown as WebSocket
      },
      random: () => 0.5, // no jitter
      onlineEvents: network,
    })
    client.connect()
    return client
  }

  const latest = () => sockets[sockets.length - 1]

  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', FakeSocket)
    sockets = []
    states = []
    network = new EventTarget()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.resetAllMocks()
  })

  it('delivers parsed events and ignores malformed frames', () => {
    connect()
    latest().serverOpens()
    latest().serverSends({ type: 'pong', data: {} })
    latest().onmessage?.({ data: 'not json' })

    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith({ type: 'pong', data: {} })
  })

  it('reconnects with growing delays and resets them after a successful open', () => {
    connect()
    latest().serverCloses(1006)
    expect(states).toEqual(['connecting', 'reconnecting'])

    vi.advanceTimersByTime(499)
    expect(sockets).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(sockets).toHaveLength(2) // after 500 ms

    latest().serverCloses(1006)
    vi.advanceTimersByTime(999)
    expect(sockets).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(sockets).toHaveLength(3) // after 1000 ms

    latest().serverOpens()
    latest().serverCloses(1006)
    vi.advanceTimersByTime(500)
    expect(sockets).toHaveLength(4) // back to 500 ms
  })

  it('reconnects at once when the browser comes back online', () => {
    connect()
    latest().serverCloses(1006)

    network.dispatchEvent(new Event('online'))

    expect(sockets).toHaveLength(2)
  })

  it('drops the socket when the browser goes offline and reopens when it is back', () => {
    connect()
    latest().serverOpens()

    network.dispatchEvent(new Event('offline'))
    expect(sockets[0].readyState).toBe(3)
    expect(states.at(-1)).toBe('reconnecting')

    latest().serverCloses(1000) // the late close event of the dropped socket is ignored
    expect(sockets).toHaveLength(1)

    network.dispatchEvent(new Event('online'))
    expect(sockets).toHaveLength(2)
  })

  it('stops for good on 4403', () => {
    connect()
    latest().serverCloses(CLOSE_FORBIDDEN)
    vi.advanceTimersByTime(60_000)

    expect(sockets).toHaveLength(1)
    expect(onForbidden).toHaveBeenCalledTimes(1)
    expect(states.at(-1)).toBe('closed')
  })

  it('refreshes the session once on 4401, then reconnects', async () => {
    refreshSession.mockResolvedValue(true)
    connect()
    latest().serverCloses(CLOSE_UNAUTHORIZED)

    await vi.waitFor(() => expect(sockets).toHaveLength(2))
    expect(refreshSession).toHaveBeenCalledTimes(1)
  })

  it('gives up when the session stays invalid after a refresh', async () => {
    refreshSession.mockResolvedValue(true)
    connect()
    latest().serverCloses(CLOSE_UNAUTHORIZED)
    await vi.waitFor(() => expect(sockets).toHaveLength(2))

    latest().serverCloses(CLOSE_UNAUTHORIZED)
    vi.advanceTimersByTime(60_000)

    expect(sockets).toHaveLength(2)
    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(states.at(-1)).toBe('closed')
  })

  it('stops when the refresh says the session is over', async () => {
    refreshSession.mockResolvedValue(false)
    connect()
    latest().serverCloses(CLOSE_UNAUTHORIZED)

    await vi.waitFor(() => expect(states.at(-1)).toBe('closed'))
    expect(sockets).toHaveLength(1)
  })

  it('pings every 25 s while open', () => {
    connect()
    latest().serverOpens()
    vi.advanceTimersByTime(50_000)

    expect(latest().sent).toEqual(['{"type":"ping"}', '{"type":"ping"}'])
  })

  it('does not reconnect after close()', () => {
    const client = connect()
    latest().serverOpens()
    client.close()
    latest().serverCloses(1000)
    vi.advanceTimersByTime(60_000)

    expect(sockets).toHaveLength(1)
  })
})
