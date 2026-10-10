import { cn } from 'cn'
import { MicIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Kbd } from '@/shared/ui/kbd'
import { Progress } from '@/shared/ui/progress'

import { MicrophoneBlockedError, type Recording, Recorder } from '../recorder'

export const MIN_RECORDING_MS = 500
export const MAX_RECORDING_MS = 60_000

interface PttButtonProps {
  onRecorded: (recording: Recording) => void
  onRecordingChange?: (recording: boolean) => void
  disabled?: boolean
}

function seconds(ms: number): string {
  const total = Math.floor(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

/** Hold to talk (pointer or Space), release to send. Stops by itself at 60 s. */
export function PttButton({ onRecorded, onRecordingChange, disabled }: PttButtonProps) {
  const recorder = useRef(new Recorder())
  const holding = useRef(false)
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [hint, setHint] = useState<string | null>(null)

  const setRecordingState = useCallback(
    (next: boolean) => {
      setRecording(next)
      onRecordingChange?.(next)
    },
    [onRecordingChange],
  )

  const finish = useCallback(async () => {
    holding.current = false
    if (!recorder.current.recording) return
    const result = await recorder.current.stop()
    setRecordingState(false)
    if (result.durationMs < MIN_RECORDING_MS) {
      setHint('Hold the button a little longer to record.')
      return
    }
    onRecorded(result)
  }, [onRecorded, setRecordingState])

  const begin = useCallback(async () => {
    if (holding.current || disabled) return
    holding.current = true
    setHint(null)
    try {
      await recorder.current.start()
    } catch (error) {
      holding.current = false
      setHint(error instanceof MicrophoneBlockedError ? error.message : 'The microphone could not be started.')
      return
    }
    // Released while the microphone was still starting.
    if (!holding.current) {
      recorder.current.cancel()
      return
    }
    setElapsed(0)
    setRecordingState(true)
  }, [disabled, setRecordingState])

  // Elapsed time, and the 60 s limit.
  useEffect(() => {
    if (!recording) return
    const startedAt = performance.now()
    const timer = setInterval(() => {
      const ms = performance.now() - startedAt
      setElapsed(ms)
      if (ms >= MAX_RECORDING_MS) void finish()
    }, 100)
    return () => clearInterval(timer)
  }, [recording, finish])

  // Space bar talks too, unless the user is typing somewhere.
  useEffect(() => {
    const typing = (target: EventTarget | null) =>
      target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA'].includes(target.tagName))
    const down = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || event.repeat || typing(event.target)) return
      event.preventDefault()
      void begin()
    }
    const up = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || typing(event.target)) return
      event.preventDefault()
      void finish()
    }
    // Losing focus while holding (alt-tab) must not leave the microphone open.
    const blur = () => void finish()
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', blur)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', blur)
    }
  }, [begin, finish])

  useEffect(() => () => recorder.current.cancel(), [])

  return (
    <div className="flex flex-col items-center gap-2 border-t px-4 py-3">
      {recording ? (
        <div className="flex w-full max-w-sm items-center gap-3 text-sm" aria-live="polite">
          <span className="font-medium text-red-500 tabular-nums">{seconds(elapsed)}</span>
          <Progress value={(elapsed / MAX_RECORDING_MS) * 100} className="h-1.5" aria-label="Recording time" />
          <span className="text-muted-foreground tabular-nums">{seconds(MAX_RECORDING_MS)}</span>
        </div>
      ) : (
        <p className={cn('text-sm', hint ? 'text-destructive' : 'text-muted-foreground')} role={hint ? 'alert' : undefined}>
          {hint ?? (
            <>
              Hold to talk, release to send · or hold <Kbd>Space</Kbd>
            </>
          )}
        </p>
      )}
      <button
        type="button"
        disabled={disabled}
        aria-label={recording ? 'Recording: release to send' : 'Hold to talk'}
        aria-pressed={recording}
        className={cn(
          'grid size-16 touch-none place-items-center rounded-full text-primary-foreground shadow-md transition select-none',
          'focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50',
          recording ? 'scale-110 animate-pulse bg-red-500' : 'bg-primary hover:bg-primary/90',
        )}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId)
          void begin()
        }}
        onPointerUp={() => void finish()}
        onPointerCancel={() => void finish()}
        onContextMenu={(event) => event.preventDefault()}
      >
        <MicIcon className="size-7" />
      </button>
    </div>
  )
}
