import { cn } from 'cn'

import type { SocketState } from '@/shared/lib/ws/ws-client'

const LABELS: Record<SocketState, string> = {
  connecting: 'Connecting…',
  open: 'Live',
  reconnecting: 'Reconnecting…',
  closed: 'Offline',
}

export function ConnectionStatus({ state }: { state: SocketState }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
      <span
        className={cn(
          'size-2 rounded-full',
          state === 'open' && 'bg-green-500',
          (state === 'connecting' || state === 'reconnecting') && 'animate-pulse bg-amber-500',
          state === 'closed' && 'bg-muted-foreground/40',
        )}
      />
      {LABELS[state]}
    </span>
  )
}
