import { MonitorSpeakerIcon, Volume2Icon } from 'lucide-react'

import { Button } from '@/shared/ui/button'

import type { QueueSnapshot } from '../playback-queue'

/** Browsers block audio until the first tap: say so, and say how much is waiting. */
export function AudioUnlockBanner({ snapshot }: { snapshot: QueueSnapshot }) {
  if (snapshot.state !== 'locked' || snapshot.waiting === 0) return null
  const count = snapshot.waiting === 1 ? '1 new message' : `${snapshot.waiting} new messages`
  return (
    <div className="flex items-center justify-center gap-3 border-b bg-primary/10 px-4 py-2 text-sm" role="status">
      <Volume2Icon className="size-4 text-primary" />
      <span>{count} waiting.</span>
      {/* Any tap unlocks; the button makes that obvious. */}
      <Button size="xs">Tap to listen</Button>
    </div>
  )
}

/** Another tab or device of the user plays this channel; this one can take over. */
export function PlayHereBanner({ snapshot, onPlayHere }: { snapshot: QueueSnapshot; onPlayHere: () => void }) {
  if (snapshot.state !== 'inactive') return null
  return (
    <div className="flex items-center justify-center gap-3 border-b bg-muted px-4 py-2 text-sm" role="status">
      <MonitorSpeakerIcon className="size-4 text-muted-foreground" />
      <span>Playing in another tab or device.</span>
      <Button size="xs" variant="outline" onClick={onPlayHere}>
        Play here
      </Button>
    </div>
  )
}
