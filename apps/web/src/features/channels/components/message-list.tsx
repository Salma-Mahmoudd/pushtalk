import { cn } from 'cn'
import { AlertCircleIcon, PlayIcon, RotateCwIcon, SquareIcon } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { Button } from '@/shared/ui/button'
import { Spinner } from '@/shared/ui/spinner'

import type { ChatMessage, Transcript } from '../message-store'
import { ReceiptDetails } from './receipt-details'

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

/** The text of a message under its bubble: arrives a moment after the audio. */
function TranscriptView({ transcript }: { transcript: Transcript }) {
  const base = 'w-64 max-w-full px-3 text-xs sm:w-72'
  if (transcript.status === 'pending') {
    return (
      <p className={cn(base, 'flex items-center gap-1 text-muted-foreground')}>
        <Spinner className="size-3" /> Transcribing…
      </p>
    )
  }
  if (transcript.status === 'failed') return <p className={cn(base, 'text-muted-foreground')}>Transcript unavailable</p>
  if (!transcript.text) return <p className={cn(base, 'text-muted-foreground')}>No speech detected</p>
  // lang and dir="auto": right-to-left languages such as Arabic display correctly.
  return (
    <p className={cn(base, 'text-foreground/80')} lang={transcript.lang ?? undefined} dir="auto">
      {transcript.text}
    </p>
  )
}

function ReadyStatus({ message }: { message: ChatMessage }) {
  const receipts = message.receipts
  let label = 'Sent'
  if (receipts && receipts.total > 0) {
    if (receipts.played > 0) label = `Played ${receipts.played}/${receipts.total}`
    else if (receipts.delivered > 0) label = `Delivered ${receipts.delivered}/${receipts.total}`
  }
  if (!message.id) return <span>{label}</span>
  return (
    <ReceiptDetails
      messageId={message.id}
      trigger={
        <button type="button" className="underline-offset-2 hover:underline">
          {label}
        </button>
      }
    />
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
          <AlertCircleIcon className="size-3" />
          {message.failureReason === 'invalid_audio' ? 'The recording could not be processed.' : (message.failureReason ?? 'Failed')}
          <Button variant="link" size="xs" className="h-auto p-0 text-destructive" onClick={onRetry} disabled={!message.upload}>
            <RotateCwIcon className="size-3" /> Retry
          </Button>
        </span>
      )
    case 'ready':
      return <ReadyStatus message={message} />
  }
}

interface BubbleProps {
  message: ChatMessage
  own: boolean
  playing: boolean
  onPlay: () => void
  onStop: () => void
  onRetry: () => void
}

function MessageBubble({ message, own, playing, onPlay, onStop, onRetry }: BubbleProps) {
  const playable = message.status === 'ready' && message.id !== null
  return (
    <li className={cn('flex flex-col gap-1', own ? 'items-end' : 'items-start')}>
      {!own && <span className="px-3 text-xs font-medium text-muted-foreground">{message.sender.username}</span>}
      <div
        className={cn(
          'flex w-64 max-w-full items-center gap-2 rounded-3xl px-2 py-2 transition-shadow sm:w-72',
          own ? 'bg-primary text-primary-foreground' : 'bg-muted',
          playing && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
          message.status === 'failed' && 'opacity-70',
        )}
        aria-current={playing ? 'true' : undefined}
      >
        <Button
          size="icon-sm"
          variant={own ? 'secondary' : 'default'}
          className="shrink-0 rounded-full"
          disabled={!playable}
          aria-label={playing ? 'Stop' : 'Play'}
          onClick={playing ? onStop : onPlay}
        >
          {playing ? <SquareIcon /> : <PlayIcon />}
        </Button>
        <Waveform peaks={message.waveform} own={own} />
        <span className="w-9 shrink-0 text-end text-xs tabular-nums">{duration(message.durationMs)}</span>
      </div>
      {message.status === 'ready' && message.transcript && <TranscriptView transcript={message.transcript} />}
      {own && (
        <span className="px-3 text-xs text-muted-foreground">
          <Status message={message} onRetry={onRetry} />
        </span>
      )}
    </li>
  )
}

interface MessageListProps {
  messages: ChatMessage[]
  currentUserId: string | undefined
  playingId: string | null
  onPlay: (message: ChatMessage) => void
  onStop: () => void
  onRetry: (message: ChatMessage) => void
  header?: React.ReactNode
}

export function MessageList({ messages, currentUserId, playingId, onPlay, onStop, onRetry, header }: MessageListProps) {
  const bottom = useRef<HTMLDivElement>(null)
  const newest = messages.at(-1)?.clientMsgId

  // Follow new messages at the bottom; loading older pages keeps the position.
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [newest])

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <div className="mx-auto max-w-2xl">
        {header}
        <ol className="flex flex-col gap-3" aria-label="Messages">
          {messages.map((message) => (
            <MessageBubble
              key={message.clientMsgId}
              message={message}
              own={message.sender.id === currentUserId}
              playing={message.id !== null && message.id === playingId}
              onPlay={() => onPlay(message)}
              onStop={onStop}
              onRetry={() => onRetry(message)}
            />
          ))}
        </ol>
      </div>
      <div ref={bottom} />
    </div>
  )
}
