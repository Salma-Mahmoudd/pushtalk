import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const PLAYBACK_RATES = [1, 1.5, 2] as const
export type PlaybackRate = (typeof PLAYBACK_RATES)[number]

interface PlaybackSettings {
  rate: PlaybackRate
  setRate: (rate: PlaybackRate) => void
}

/** The listener's playback speed, kept in localStorage across reloads and shared by all rooms. */
export const usePlaybackSettings = create<PlaybackSettings>()(
  persist(
    (set) => ({
      rate: 1,
      setRate: (rate) => set({ rate }),
    }),
    {
      name: 'pushtalk-playback',
      version: 1,
      partialize: ({ rate }) => ({ rate }),
      // A stored value that is not one of the offered speeds falls back to 1×.
      merge: (stored, current) => {
        const rate = (stored as Partial<PlaybackSettings> | undefined)?.rate
        return PLAYBACK_RATES.includes(rate as PlaybackRate) ? { ...current, rate: rate as PlaybackRate } : current
      },
    },
  ),
)
