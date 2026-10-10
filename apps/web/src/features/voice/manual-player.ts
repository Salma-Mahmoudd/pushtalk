/** Plays one message at a time: starting another one stops the current one. */
let current: HTMLAudioElement | null = null

export function playExclusive(src: string, onEnded: () => void): HTMLAudioElement {
  current?.pause()
  const audio = new Audio(src)
  audio.addEventListener('ended', () => {
    if (current === audio) current = null
    onEnded()
  })
  current = audio
  void audio.play().catch(onEnded)
  return audio
}

export function stopPlayback(): void {
  current?.pause()
  current = null
}
