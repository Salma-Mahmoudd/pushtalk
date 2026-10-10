import { useEffect, useState } from 'react'

import { refreshOnce } from '@/shared/lib/api/client'

import { HtmlAudioPlayer } from './html-audio-player'
import { PlaybackQueue, type QueueItem, type QueueSnapshot } from './playback-queue'
import { usePlaybackSettings } from './playback-settings'

/** One playback queue for the open room; the first tap or key press anywhere unlocks audio. */
export function usePlayback(onPlayed: (item: QueueItem) => void): { queue: PlaybackQueue; snapshot: QueueSnapshot } {
  const [snapshot, setSnapshot] = useState<QueueSnapshot>({
    state: 'locked',
    currentId: null,
    waiting: 0,
    recording: false,
  })
  const [queue] = useState(
    () =>
      new PlaybackQueue({
        player: new HtmlAudioPlayer(refreshOnce),
        onChange: setSnapshot,
      }),
  )

  const rate = usePlaybackSettings((settings) => settings.rate)
  useEffect(() => {
    queue.setRate(rate)
  }, [queue, rate])

  useEffect(() => {
    queue.setOnPlayed(onPlayed)
  }, [queue, onPlayed])

  useEffect(() => {
    // Already clicked something on this page (e.g. the channel link): no banner needed.
    if (navigator.userActivation?.hasBeenActive) queue.unlock()
    const unlock = () => queue.unlock()
    window.addEventListener('pointerdown', unlock, { capture: true })
    window.addEventListener('keydown', unlock, { capture: true })
    return () => {
      window.removeEventListener('pointerdown', unlock, { capture: true })
      window.removeEventListener('keydown', unlock, { capture: true })
      queue.stopCurrent()
    }
  }, [queue])

  return { queue, snapshot }
}
