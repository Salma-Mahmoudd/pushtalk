import { useQuery } from '@tanstack/react-query'
import { CheckCheckIcon, CheckIcon, ClockIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { apiRequest } from '@/shared/lib/api/client'
import type { components } from '@/shared/lib/api/schema'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/shared/ui/dialog'
import { Spinner } from '@/shared/ui/spinner'

type RecipientReceipt = components['schemas']['RecipientReceipt']

const time = (value: string) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

function Row({ receipt }: { receipt: RecipientReceipt }) {
  let status: ReactNode = (
    <span className="flex items-center gap-1 text-muted-foreground">
      <ClockIcon className="size-4" /> Not received yet
    </span>
  )
  if (receipt.played_at) {
    status = (
      <span className="flex items-center gap-1 text-primary">
        <CheckCheckIcon className="size-4" /> Played {time(receipt.played_at)}
      </span>
    )
  } else if (receipt.delivered_at) {
    status = (
      <span className="flex items-center gap-1">
        <CheckIcon className="size-4" /> Delivered {time(receipt.delivered_at)}
      </span>
    )
  }
  return (
    <li className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="font-medium">{receipt.username}</span>
      {status}
    </li>
  )
}

/** Per-recipient delivered and played times of one of the user's messages; updates live. */
export function ReceiptDetails({ messageId, trigger }: { messageId: string; trigger: ReactNode }) {
  return (
    <Dialog>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Message status</DialogTitle>
          <DialogDescription>Who received and played this message.</DialogDescription>
        </DialogHeader>
        <Recipients messageId={messageId} />
      </DialogContent>
    </Dialog>
  )
}

function Recipients({ messageId }: { messageId: string }) {
  const receipts = useQuery({
    queryKey: ['receipts', messageId],
    queryFn: () => apiRequest<RecipientReceipt[]>(`/api/messages/${messageId}/receipts`),
  })
  if (receipts.isPending) return <Spinner className="mx-auto" />
  if (!receipts.data?.length) return <p className="text-sm text-muted-foreground">Nobody else is in this channel yet.</p>
  return (
    <ul className="divide-y">
      {receipts.data.map((receipt) => (
        <Row key={receipt.user_id} receipt={receipt} />
      ))}
    </ul>
  )
}
