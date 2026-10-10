import { beforeEach, describe, expect, it, vi } from 'vitest'

import { type AudioPlayer, PlaybackQueue, type QueueItem } from './playback-queue'

/** Records what the queue asks of the player; tests end or fail playback by hand. */
class FakeAudioPlayer implements AudioPlayer {
  played: string[] = []
  playing: string | null = null
  paused = false
  failNext = false
  unlocked = false
  rate = 1
  private ended: () => void = () => {}
  private errored: () => void = () => {}

  play = vi.fn(async (src: string) => {
    if (this.failNext) {
      this.failNext = false
      throw new Error('cannot load')
    }
    this.played.push(src)
    this.playing = src
    this.paused = false
  })
  pause = vi.fn(() => {
    this.paused = true
  })
  resume = vi.fn(async () => {
    this.paused = false
  })
  stop = vi.fn(() => {
    this.playing = null
  })
  setRate = vi.fn((rate: number) => {
    this.rate = rate
  })
  unlock = vi.fn(async () => {
    this.unlocked = true
  })
  onEnded(callback: () => void) {
    this.ended = callback
  }
  onError(callback: () => void) {
    this.errored = callback
  }

  end() {
    this.playing = null
    this.ended()
  }
  error() {
    this.playing = null
    this.errored()
  }
}

const item = (seq: number, own = false): QueueItem => ({ id: `m${seq}`, seq, src: `/a/${seq}`, own })
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('PlaybackQueue', () => {
  let player: FakeAudioPlayer
  let onPlayed: ReturnType<typeof vi.fn<(item: QueueItem) => void>>
  let queue: PlaybackQueue

  beforeEach(() => {
    player = new FakeAudioPlayer()
    onPlayed = vi.fn<(item: QueueItem) => void>()
    queue = new PlaybackQueue({ player, onPlayed })
    queue.unlock()
  })

  it('plays in seq order even when messages arrive out of order', () => {
    queue.recordingStarted() // hold playback while the three arrive
    queue.enqueue(item(3))
    queue.enqueue(item(1))
    queue.enqueue(item(2))
    queue.recordingStopped()

    player.end()
    player.end()

    expect(player.played).toEqual(['/a/1', '/a/2', '/a/3'])
  })

  it('never plays two messages at once', () => {
    queue.enqueue(item(1))
    queue.enqueue(item(2))

    expect(player.played).toEqual(['/a/1'])
    expect(queue.snapshot()).toMatchObject({ state: 'playing', currentId: 'm1', waiting: 1 })

    player.end()
    expect(player.played).toEqual(['/a/1', '/a/2'])
  })

  it("skips the listener's own messages and duplicate seqs", () => {
    queue.enqueue(item(1, true))
    queue.enqueue(item(2))
    queue.enqueue(item(2)) // the same message again (catch-up after a live event)

    player.end()

    expect(player.played).toEqual(['/a/2'])
    expect(queue.snapshot().waiting).toBe(0)
  })

  it('buffers while locked and drains in order after unlock', () => {
    const locked = new PlaybackQueue({ player, onPlayed })
    locked.enqueue(item(2))
    locked.enqueue(item(1))

    expect(player.play).not.toHaveBeenCalled()
    expect(locked.snapshot()).toMatchObject({ state: 'locked', waiting: 2 })

    locked.unlock()
    expect(player.unlocked).toBe(true)
    player.end()
    expect(player.played).toEqual(['/a/1', '/a/2'])
  })

  it('pauses while recording, resumes the same message after, then continues', () => {
    queue.enqueue(item(1))
    queue.enqueue(item(2))

    queue.recordingStarted()
    expect(player.pause).toHaveBeenCalled()
    expect(queue.snapshot().state).toBe('suspended')

    queue.recordingStopped()
    expect(player.resume).toHaveBeenCalled()
    expect(player.played).toEqual(['/a/1']) // resumed, not restarted

    player.end()
    expect(player.played).toEqual(['/a/1', '/a/2'])
  })

  it('does not start anything while recording', () => {
    queue.recordingStarted()
    queue.enqueue(item(1))

    expect(player.play).not.toHaveBeenCalled()
    queue.recordingStopped()
    expect(player.played).toEqual(['/a/1'])
  })

  it('skips a message that fails to load instead of stalling', async () => {
    player.failNext = true
    queue.enqueue(item(1))
    queue.enqueue(item(2))
    await flush()

    expect(player.played).toEqual(['/a/2'])
    expect(onPlayed).not.toHaveBeenCalled()
  })

  it('skips a message whose playback errors midway', () => {
    queue.enqueue(item(1))
    queue.enqueue(item(2))
    player.error()

    expect(player.played).toEqual(['/a/1', '/a/2'])
    expect(onPlayed).not.toHaveBeenCalled()
  })

  it('reports each played message exactly once', () => {
    queue.enqueue(item(1))
    queue.enqueue(item(2))
    player.end()
    player.end()
    player.end() // a stray ended event changes nothing

    expect(onPlayed.mock.calls.map(([played]) => played.seq)).toEqual([1, 2])
  })

  it('goes quiet when another tab takes over and continues when this tab is back', () => {
    queue.enqueue(item(1))
    queue.setActive(false)

    expect(player.stop).toHaveBeenCalled()
    expect(queue.snapshot()).toMatchObject({ state: 'inactive', waiting: 1 })

    queue.enqueue(item(2))
    queue.setActive(true)
    expect(player.played).toEqual(['/a/1', '/a/1']) // the interrupted message starts over
    player.end()
    expect(player.played.at(-1)).toBe('/a/2')
  })

  it('plays a picked message now and puts the interrupted one back in line', () => {
    queue.enqueue(item(5))
    queue.playNow(item(2))

    expect(player.played).toEqual(['/a/5', '/a/2'])
    player.end()
    expect(player.played).toEqual(['/a/5', '/a/2', '/a/5'])
  })

  it('moves on when the user stops the playing message', () => {
    queue.enqueue(item(1))
    queue.enqueue(item(2))
    queue.stopCurrent()

    expect(player.played).toEqual(['/a/1', '/a/2'])
    expect(onPlayed).not.toHaveBeenCalled()
  })

  it('changes speed mid-message without restarting, and keeps it for the next ones', () => {
    queue.enqueue(item(1))
    queue.enqueue(item(2))
    queue.setRate(1.5)

    expect(player.rate).toBe(1.5)
    expect(player.played).toEqual(['/a/1']) // not restarted
    player.end()
    expect(player.played).toEqual(['/a/1', '/a/2'])
    expect(player.rate).toBe(1.5)
  })
})
