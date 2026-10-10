import { cn } from 'cn'
import { AlertCircleIcon, PauseIcon, PlayIcon, RotateCwIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { playExclusive, stopPlayback } from '@/features/voice/manual-player'
import { Button } from '@/shared/ui/button'
import { Spinner } from '@/shared/ui/spinner'

import type { ChatMessage } from '../message-store'

function duration(ms: number | null): string {
  if (ms === null) return '–:––'
  const total = Math.round(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

function Waveform({ peaks, own }: { peaks: number[] | null; own: boolean }) {
  const bars = peaks ?? Array.from({ length: 64 }, () => 15)
  return (
    <div className="flex h-8 flex-1 items-center gap-px" aria-hidden="true">
      {bars.map((peak, index) => (
        <span
          key={index}
          className={cn('w-full rounded-full', own ? 'bg-primary-foreground/70' : 'bg-primary/60', peaks === null && 'animate-pulse')}
          style={{ height: `${Math.max(10, peak)}%` }}
        />
      ))}
    </div>
  )
}

function Status({ message, onRetry }: { message: ChatMessage; onRetry: () => void }) {
  switch (message.status) {
    case 'uploading':
      return (
        <span className="flex items-center gap-1">
          <Spinner className="size-3" /> Uploading…
        </span>
      )
    case 'processing':
      return (
        <span className="flex items-center gap-1">
          <Spinner className="size-3" /> Sending…
        </span>
      )
    case 'failed':
      return (
        <span className="flex items-center gap-1 text-destructive" role="alert">
          <AlertCircleIcon className="size-3" /> {message.failureReason === 'invalid_audio' ? 'The recording could not be processed.' : (message.failureReason ?? 'Failed')}
          <Button variant="link" size="xs" className="h-auto p-0 text-destructive" onClick={onRetry} disabled={!message.upload}>
            <RotateCwIcon className="size-3" /> Retry
          </Button>
        </span>
      )
    case 'ready':
      return <span>Sent</span>
  }
}

function MessageBubble({ message, own, onRetry }: { message: ChatMessage; own: boolean; onRetry: () => void }) {
  const [playing, setPlaying] = useState(false)
  const playable = message.status === 'ready' && message.id !== null

  function toggle() {
    if (playing) {
      stopPlayback()
      setPlaying(false)
      return
    }
    setPlaying(true)
    playExclusive(`/api/messages/${message.id}/audio`, () => setPlaying(false))
  }

  return (
    <li className={cn('flex flex-col gap-1', own ? 'items-end' : 'items-start')}>
      {!own && <span className="px-3 text-xs font-medium text-muted-foreground">{message.sender.username}</span>}
      <div
        className={cn(
          'flex w-64 max-w-full items-center gap-2 rounded-3xl px-2 py-2 sm:w-72',
          own ? 'bg-primary text-primary-foreground' : 'bg-muted',
          message.status === 'failed' && 'opacity-70',
        )}
      >
        <Button
          size="icon-sm"
          variant={own ? 'secondary' : 'default'}
          className="shrink-0 rounded-full"
          disabled={!playable}
          aria-label={playing ? 'Pause' : 'Play'}
          onClick={toggle}
        >
          {playing ? <PauseIcon /> : <PlayIcon />}
        </Button>
        <Waveform peaks={message.waveform} own={own} />
        <span className="w-9 shrink-0 text-end text-xs tabular-nums">{duration(message.durationMs)}</span>
      </div>
      {own && (
        <span className="px-3 text-xs text-muted-foreground">
          <Status message={message} onRetry={onRetry} />
        </span>
      )}
    </li>
  )
}

export function MessageList({
  messages,
  currentUserId,
  onRetry,
}: {
  messages: ChatMessage[]
  currentUserId: string | undefined
  onRetry: (message: ChatMessage) => void
}) {
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length])

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <ol className="mx-auto flex max-w-2xl flex-col gap-3" aria-label="Messages">
        {messages.map((message) => (
          <MessageBubble
            key={message.clientMsgId}
            message={message}
            own={message.sender.id === currentUserId}
            onRetry={() => onRetry(message)}
          />
        ))}
      </ol>
      <div ref={bottom} />
    </div>
  )
}
