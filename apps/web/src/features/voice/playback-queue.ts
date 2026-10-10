/** Plays one voice message at a time, in channel order. No DOM: the player is injected. */

export interface QueueItem {
  id: string
  seq: number
  src: string
  /** The listener's own message: never played automatically. */
  own: boolean
}

export interface AudioPlayer {
  /** Starts playing; rejects if the audio cannot be loaded or played. */
  play: (src: string) => Promise<void>
  pause: () => void
  resume: () => Promise<void>
  stop: () => void
  /** Speed for the current source and every later one, pitch preserved. */
  setRate: (rate: number) => void
  /** Called from a user gesture: allows later playback without one (autoplay policy). */
  unlock: () => Promise<void>
  onEnded: (callback: () => void) => void
  onError: (callback: () => void) => void
  /** Optional: fetch the next message ahead of time. */
  preload?: (src: string) => void
}

export type QueueState = 'locked' | 'idle' | 'playing' | 'suspended' | 'inactive'

export interface QueueSnapshot {
  state: QueueState
  currentId: string | null
  waiting: number
  /** The user is talking: incoming messages are held until the button is released. */
  recording: boolean
}

interface QueueOptions {
  player: AudioPlayer
  /** Fired once for each item that played to the end; replaceable with setOnPlayed. */
  onPlayed?: (item: QueueItem) => void
  onChange?: (snapshot: QueueSnapshot) => void
}

export class PlaybackQueue {
  private readonly options: QueueOptions
  private onPlayed: (item: QueueItem) => void
  private items: QueueItem[] = []
  private readonly seen = new Set<number>()
  private current: QueueItem | null = null
  private locked = true
  private recording = false
  private active = true

  constructor(options: QueueOptions) {
    this.options = options
    this.onPlayed = options.onPlayed ?? (() => undefined)
    options.player.onEnded(() => this.finish(true))
    options.player.onError(() => this.finish(false))
  }

  /** Swaps the played callback, e.g. when the component that owns the queue re-renders. */
  setOnPlayed(onPlayed: (item: QueueItem) => void): void {
    this.onPlayed = onPlayed
  }

  /** Adds a message; duplicates (same seq) and the listener's own messages are ignored. */
  enqueue(item: QueueItem): void {
    if (item.own || this.seen.has(item.seq)) return
    this.seen.add(item.seq)
    this.insert(item)
    this.advance()
  }

  /** Playback speed: changes the playing message without restarting it, and applies to all later ones. */
  setRate(rate: number): void {
    this.options.player.setRate(rate)
  }

  /** First user gesture: buffered messages start playing in order. */
  unlock(): void {
    if (!this.locked) return
    this.locked = false
    void this.options.player.unlock()
    this.advance()
  }

  /** Half-duplex: incoming audio waits while the user talks. */
  recordingStarted(): void {
    this.recording = true
    if (this.current) this.options.player.pause()
    this.emit()
  }

  recordingStopped(): void {
    this.recording = false
    if (this.current && this.active) {
      void this.options.player.resume().catch(() => this.finish(false))
      this.emit()
    } else {
      this.advance()
    }
  }

  /** Only the user's active tab plays; others keep their queue for when they take over. */
  setActive(active: boolean): void {
    if (active === this.active) return
    this.active = active
    if (!active && this.current) {
      this.options.player.stop()
      this.insert(this.current)
      this.current = null
    }
    this.advance()
  }

  /** The user picked a message: it plays now; an interrupted message goes back in line. */
  playNow(item: QueueItem): void {
    this.seen.add(item.seq)
    this.items = this.items.filter((queued) => queued.seq !== item.seq)
    if (this.current) {
      this.options.player.stop()
      if (!this.current.own && this.current.seq !== item.seq) this.insert(this.current)
    }
    this.start(item)
  }

  /** The user stopped the playing message: it counts as skipped, the queue goes on. */
  stopCurrent(): void {
    if (!this.current) return
    this.options.player.stop()
    this.current = null
    this.advance()
  }

  snapshot(): QueueSnapshot {
    let state: QueueState = 'idle'
    // Inactive first: a silent tab offers "Play here" even before its first tap (the tap unlocks too).
    if (!this.active) state = 'inactive'
    else if (this.locked) state = 'locked'
    else if (this.recording && this.current) state = 'suspended'
    else if (this.current) state = 'playing'
    return { state, currentId: this.current?.id ?? null, waiting: this.items.length, recording: this.recording }
  }

  private insert(item: QueueItem): void {
    const index = this.items.findIndex((queued) => queued.seq > item.seq)
    if (index === -1) this.items.push(item)
    else this.items.splice(index, 0, item)
  }

  private advance(): void {
    if (this.locked || this.recording || !this.active || this.current) {
      this.emit()
      return
    }
    const next = this.items.shift()
    if (next) this.start(next)
    else this.emit()
  }

  private start(item: QueueItem): void {
    this.current = item
    this.emit()
    this.options.player.play(item.src).catch(() => {
      if (this.current === item) this.finish(false)
    })
    if (this.items[0]) this.options.player.preload?.(this.items[0].src)
  }

  private finish(played: boolean): void {
    const item = this.current
    if (!item) return
    this.current = null
    if (played) this.onPlayed(item)
    this.advance()
  }

  private emit(): void {
    this.options.onChange?.(this.snapshot())
  }
}
