import { ToggleGroup, ToggleGroupItem } from '@/shared/ui/toggle-group'

import { PLAYBACK_RATES, type PlaybackRate, usePlaybackSettings } from '../playback-settings'

/** 1× / 1.5× / 2×: applies to the message playing now and every later one. */
export function SpeedControl() {
  const rate = usePlaybackSettings((settings) => settings.rate)
  const setRate = usePlaybackSettings((settings) => settings.setRate)
  return (
    <ToggleGroup
      type="single"
      size="sm"
      variant="outline"
      spacing={0}
      value={String(rate)}
      onValueChange={(value) => value && setRate(Number(value) as PlaybackRate)}
      aria-label="Playback speed"
    >
      {PLAYBACK_RATES.map((option) => (
        <ToggleGroupItem key={option} value={String(option)} className="px-2 text-xs tabular-nums" aria-label={`${option}× speed`}>
          {option}×
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}
