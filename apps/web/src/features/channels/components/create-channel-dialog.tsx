import { type FormEvent, type ReactNode, useState } from 'react'
import { useNavigate } from 'react-router'

import { ApiError } from '@/shared/lib/api/client'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/shared/ui/dialog'
import { Field, FieldError, FieldLabel } from '@/shared/ui/field'
import { Input } from '@/shared/ui/input'
import { Spinner } from '@/shared/ui/spinner'

import { useCreateChannel } from '../queries'

export function CreateChannelDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const createChannel = useCreateChannel()
  const navigate = useNavigate()

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get('name'))
    const channel = await createChannel.mutateAsync(name).catch(() => null)
    if (channel) {
      setOpen(false)
      navigate(`/channels/${channel.id}`)
    }
  }

  const error = createChannel.error instanceof ApiError ? createChannel.error : null
  const nameError = error?.code === 'channel_exists' ? error.message : (error?.fieldMessage('name') ?? error?.message)

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) createChannel.reset()
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <form onSubmit={onSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Create a channel</DialogTitle>
            <DialogDescription>Everyone can find and join it.</DialogDescription>
          </DialogHeader>
          <Field data-invalid={Boolean(nameError)}>
            <FieldLabel htmlFor="channel-name">Name</FieldLabel>
            <Input id="channel-name" name="name" required maxLength={50} autoComplete="off" aria-invalid={Boolean(nameError)} />
            <FieldError>{nameError}</FieldError>
          </Field>
          <DialogFooter>
            <Button type="submit" disabled={createChannel.isPending}>
              {createChannel.isPending && <Spinner />}
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
