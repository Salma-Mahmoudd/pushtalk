import { nextDelay } from './backoff'

export type SocketState = 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface SocketEvent {
  type: string
  data: Record<string, unknown>
}

/** Missing, expired or revoked session: refresh, then reconnect. */
export const CLOSE_UNAUTHORIZED = 4401
/** No access to this resource: reconnecting would not help. */
export const CLOSE_FORBIDDEN = 4403

export interface WsClientOptions {
  /** Called on every (re)connect, so the address can carry fresh state (e.g. since_seq). */
  url: () => string
  onEvent: (event: SocketEvent) => void
  onStateChange?: (state: SocketState) => void
  /** Renews the session after a 4401 close; resolves false when the session is over. */
  refreshSession: () => Promise<boolean>
  onForbidden?: () => void
  pingIntervalMs?: number
  /** Injectable for tests. */
  createSocket?: (url: string) => WebSocket
  /** Where the browser's "online" and "offline" events fire; defaults to window. */
  onlineEvents?: EventTarget
  random?: () => number
}

/** Absolute ws:// or wss:// address for a path on this site. */
export function socketUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

/**
 * One logical connection that survives drops: reconnects with exponential backoff (at once
 * when the browser comes back online), refreshes the session once on 4401 and stops on 4403.
 * Going offline drops the socket right away instead of waiting for a dead TCP connection to time out.
 */
export class WsClient {
  private readonly options: WsClientOptions
  private socket: WebSocket | null = null
  private state: SocketState = 'closed'
  private attempt = 0
  private stopped = true
  private refreshedSinceOpen = false
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined
  private pingTimer: ReturnType<typeof setInterval> | undefined

  constructor(options: WsClientOptions) {
    this.options = options
  }

  connect(): void {
    this.stopped = false
    this.onlineEvents()?.addEventListener('online', this.onOnline)
    this.onlineEvents()?.addEventListener('offline', this.onOffline)
    this.open('connecting')
  }

  close(): void {
    this.stop()
    this.socket?.close(1000)
    this.socket = null
  }

  /** Sends when connected; returns false otherwise (callers decide whether to retry). */
  send(event: { type: string; data?: Record<string, unknown> }): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false
    this.socket.send(JSON.stringify(event))
    return true
  }

  private open(state: SocketState): void {
    clearTimeout(this.reconnectTimer)
    this.setState(state)
    const socket = (this.options.createSocket ?? ((url) => new WebSocket(url)))(this.options.url())
    this.socket = socket
    socket.onopen = () => {
      this.attempt = 0
      this.refreshedSinceOpen = false
      this.setState('open')
      this.pingTimer = setInterval(() => this.send({ type: 'ping' }), this.options.pingIntervalMs ?? 25_000)
    }
    socket.onmessage = (message: MessageEvent<string>) => {
      let event: SocketEvent
      try {
        event = JSON.parse(message.data) as SocketEvent
      } catch {
        return
      }
      this.options.onEvent(event)
    }
    socket.onclose = (close: CloseEvent) => {
      if (this.socket !== socket) return
      clearInterval(this.pingTimer)
      this.socket = null
      if (!this.stopped) this.handleClose(close.code)
    }
  }

  private handleClose(code: number): void {
    if (code === CLOSE_FORBIDDEN) {
      this.stop()
      this.options.onForbidden?.()
      return
    }
    if (code === CLOSE_UNAUTHORIZED) {
      // One refresh per successful connection, so a session that stays invalid cannot loop.
      if (this.refreshedSinceOpen) {
        this.stop()
        return
      }
      this.refreshedSinceOpen = true
      this.setState('reconnecting')
      this.options.refreshSession().then(
        (renewed) => {
          if (this.stopped) return
          if (renewed) this.open('reconnecting')
          else this.stop()
        },
        () => this.scheduleReconnect(),
      )
      return
    }
    this.scheduleReconnect()
  }

  private scheduleReconnect(): void {
    if (this.stopped) return
    this.setState('reconnecting')
    const delay = nextDelay(this.attempt++, { random: this.options.random })
    this.reconnectTimer = setTimeout(() => this.open('reconnecting'), delay)
  }

  private readonly onOnline = () => {
    if (this.state === 'reconnecting' && this.socket === null) this.open('reconnecting')
  }

  private readonly onOffline = () => {
    const socket = this.socket
    if (!socket) return
    this.socket = null
    clearInterval(this.pingTimer)
    socket.close(1000)
    this.scheduleReconnect()
  }

  private stop(): void {
    this.stopped = true
    clearTimeout(this.reconnectTimer)
    clearInterval(this.pingTimer)
    this.onlineEvents()?.removeEventListener('online', this.onOnline)
    this.onlineEvents()?.removeEventListener('offline', this.onOffline)
    this.setState('closed')
  }

  private onlineEvents(): EventTarget | null {
    return this.options.onlineEvents ?? (typeof window === 'undefined' ? null : window)
  }

  private setState(state: SocketState): void {
    if (state === this.state) return
    this.state = state
    this.options.onStateChange?.(state)
  }
}
