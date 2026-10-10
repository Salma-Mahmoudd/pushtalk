import { HashIcon, PlusIcon, UsersIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router'

import { Button } from '@/shared/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/shared/ui/empty'
import { Spinner } from '@/shared/ui/spinner'

import type { Channel } from '../api'
import { useChannels, useJoinChannel } from '../queries'
import { CreateChannelDialog } from './create-channel-dialog'

function ChannelRow({ channel }: { channel: Channel }) {
  const join = useJoinChannel()
  const navigate = useNavigate()

  return (
    <li className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3">
      <HashIcon className="size-4 shrink-0 text-muted-foreground" />
      <span className="truncate font-medium">{channel.name}</span>
      <span className="ms-auto flex shrink-0 items-center gap-1 text-sm text-muted-foreground">
        <UsersIcon className="size-4" />
        {channel.member_count}
      </span>
      {channel.is_member ? (
        <Button variant="outline" size="sm" asChild>
          <Link to={`/channels/${channel.id}`}>Open</Link>
        </Button>
      ) : (
        <Button
          size="sm"
          disabled={join.isPending}
          onClick={() => join.mutateAsync(channel.id).then(() => navigate(`/channels/${channel.id}`))}
        >
          {join.isPending && <Spinner />}
          Join
        </Button>
      )}
    </li>
  )
}

export function BrowsePage() {
  const { data: channels, isPending } = useChannels()

  if (isPending) {
    return (
      <div className="grid flex-1 place-items-center">
        <Spinner className="size-6" />
      </div>
    )
  }

  if (!channels?.length) {
    return (
      <Empty className="flex-1">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <HashIcon />
          </EmptyMedia>
          <EmptyTitle>No channels yet</EmptyTitle>
          <EmptyDescription>Create the first one and invite others to join.</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <CreateChannelDialog
            trigger={
              <Button>
                <PlusIcon />
                Create a channel
              </Button>
            }
          />
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <section className="mx-auto w-full max-w-2xl p-4 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">Channels</h1>
        <CreateChannelDialog
          trigger={
            <Button size="sm">
              <PlusIcon />
              New channel
            </Button>
          }
        />
      </div>
      <ul className="grid gap-2">
        {channels.map((channel) => (
          <ChannelRow key={channel.id} channel={channel} />
        ))}
      </ul>
    </section>
  )
}
