import type { AudioPlayer } from './playback-queue'

/** 0.1 s of silence as a WAV blob (the Content-Security-Policy allows blob: media, not data:). */
function silentWavUrl(): string {
  const samples = 800
  const buffer = new ArrayBuffer(44 + samples * 2)
  const view = new DataView(buffer)
  const text = (offset: number, value: string) =>
    [...value].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)))
  text(0, 'RIFF')
  view.setUint32(4, 36 + samples * 2, true)
  text(8, 'WAVEfmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, 8000, true)
  view.setUint32(28, 16_000, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  text(36, 'data')
  view.setUint32(40, samples * 2, true)
  return URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }))
}

/**
 * Plays through one audio element. A source that fails to load may mean an expired access
 * cookie, so the session is renewed once and the source tried again before giving up.
 */
export class HtmlAudioPlayer implements AudioPlayer {
  private readonly audio = new Audio()
  private readonly preloader = new Audio()
  private playing = false
  private ended: () => void = () => {}
  private errored: () => void = () => {}
  private readonly renewSession: () => Promise<boolean>

  constructor(renewSession: () => Promise<boolean>) {
    this.renewSession = renewSession
    this.audio.preload = 'auto'
    this.preloader.preload = 'auto'
    this.audio.addEventListener('ended', () => {
      this.playing = false
      this.ended()
    })
    // Errors while loading are handled by play(); this covers failures mid-playback.
    this.audio.addEventListener('error', () => {
      if (!this.playing) return
      this.playing = false
      this.errored()
    })
  }

  onEnded(callback: () => void): void {
    this.ended = callback
  }

  onError(callback: () => void): void {
    this.errored = callback
  }

  async play(src: string): Promise<void> {
    this.playing = false
    try {
      await this.start(src)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'NotAllowedError') throw error
      if (!(await this.renewSession().catch(() => false))) throw error
      await this.start(src)
    }
  }

  pause(): void {
    this.audio.pause()
  }

  async resume(): Promise<void> {
    await this.audio.play()
  }

  stop(): void {
    this.playing = false
    this.audio.pause()
    this.audio.removeAttribute('src')
    this.audio.load()
  }

  async unlock(): Promise<void> {
    const url = silentWavUrl()
    this.audio.src = url
    await this.audio.play().catch(() => undefined)
    URL.revokeObjectURL(url)
  }

  preload(src: string): void {
    this.preloader.src = src
  }

  private async start(src: string): Promise<void> {
    this.audio.src = src
    await this.audio.play()
    this.playing = true
  }
}
