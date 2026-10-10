import { SearchIcon } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { ApiError } from '@/shared/lib/api/client'
import { Button } from '@/shared/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'
import { Spinner } from '@/shared/ui/spinner'

import { useOpenDirect, useUserSearch } from '../queries'

/** Waits until typing pauses, so each keystroke does not send a request. */
function useDebounced(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

export function NewDirectDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const query = useDebounced(text.trim().toLowerCase(), 250)
  const valid = /^[a-z0-9_]*$/.test(query)
  const search = useUserSearch(valid ? query : '')
  const openDirect = useOpenDirect()
  const navigate = useNavigate()

  const start = (userId: string) =>
    openDirect.mutate(userId, {
      onSuccess: (direct) => {
        setOpen(false)
        setText('')
        void navigate(`/channels/${direct.id}`)
      },
    })

  const error = openDirect.error instanceof ApiError ? openDirect.error.message : null

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>New direct message</DialogTitle>
          <DialogDescription>Talk to one person. Only the two of you hear it.</DialogDescription>
        </DialogHeader>
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            autoFocus
            className="ps-8"
            placeholder="Search by username"
            aria-label="Search by username"
            value={text}
            maxLength={32}
            onChange={(event) => setText(event.target.value)}
          />
        </div>
        <div className="min-h-24" aria-live="polite">
          {!valid && <p className="text-sm text-muted-foreground">Usernames use letters, digits and _ only.</p>}
          {valid && query && search.isPending && <Spinner className="mx-auto mt-4" />}
          {search.data?.length === 0 && <p className="text-sm text-muted-foreground">Nobody found.</p>}
          {search.data && search.data.length > 0 && (
            <ul className="flex flex-col gap-1" aria-label="Users">
              {search.data.map((user) => (
                <li key={user.id}>
                  <Button
                    variant="ghost"
                    className="w-full justify-start"
                    disabled={openDirect.isPending}
                    onClick={() => start(user.id)}
                  >
                    {openDirect.isPending && openDirect.variables === user.id && <Spinner />}
                    {user.username}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {error && (
            <p className="mt-2 text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
