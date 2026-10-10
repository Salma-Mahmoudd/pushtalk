import { HashIcon, LockIcon, MicIcon } from 'lucide-react'
import { useMemo } from 'react'
import { useParams } from 'react-router'

import { useAuthStore } from '@/features/auth/store'
import { PttButton } from '@/features/voice/components/ptt-button'
import { stopPlayback } from '@/features/voice/manual-player'

import { ApiError } from '@/shared/lib/api/client'
import { Button } from '@/shared/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/shared/ui/empty'
import { Spinner } from '@/shared/ui/spinner'

import { orderMessages, useMessageStore } from '../message-store'
import { useChannel, useJoinChannel, useMembers } from '../queries'
import { sendRecording } from '../send'
import { useChannelHistory } from '../use-channel-history'
import { useChannelSocket } from '../use-channel-socket'
import { ConnectionStatus } from './connection-status'
import { MemberList } from './member-list'
import { MessageList } from './message-list'

function JoinPrompt({ channelId }: { channelId: string }) {
  const join = useJoinChannel()
  return (
    <Empty className="flex-1">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <LockIcon />
        </EmptyMedia>
        <EmptyTitle>Join this channel to listen in</EmptyTitle>
        <EmptyDescription>Members hear every message and can talk.</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button disabled={join.isPending} onClick={() => join.mutate(channelId)}>
          {join.isPending && <Spinner />}
          Join channel
        </Button>
      </EmptyContent>
    </Empty>
  )
}

export function ChannelRoom() {
  const { channelId = '' } = useParams()
  const channel = useChannel(channelId)
  const isMember = channel.isSuccess
  const members = useMembers(channelId, isMember)
  const socket = useChannelSocket(channelId, isMember)
  useChannelHistory(channelId, socket.state, isMember)
  const user = useAuthStore((state) => state.user)
  const stored = useMessageStore((state) => state.byChannel[channelId])
  const messages = useMemo(() => orderMessages(stored), [stored])

  if (channel.isPending) {
    return (
      <div className="grid flex-1 place-items-center">
        <Spinner className="size-6" />
      </div>
    )
  }

  const error = channel.error instanceof ApiError ? channel.error : null
  if (error?.code === 'not_a_member') return <JoinPrompt channelId={channelId} />
  if (error) {
    return (
      <Empty className="flex-1">
        <EmptyHeader>
          <EmptyTitle>{error.status === 404 ? 'Channel not found' : 'Could not open this channel'}</EmptyTitle>
          <EmptyDescription>{error.message}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  const onlineCount = members.data?.filter((member) => socket.online.has(member.id)).length ?? 0

  return (
    <div className="flex min-h-0 flex-1">
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b px-4 py-3">
          <HashIcon className="size-4 text-muted-foreground" />
          <h1 className="truncate font-semibold">{channel.data?.name}</h1>
          <span className="ms-auto">
            <ConnectionStatus state={socket.state} />
          </span>
        </header>
        {messages.length > 0 ? (
          <MessageList
            messages={messages}
            currentUserId={user?.id}
            onRetry={(message) => message.upload && user && void sendRecording(channelId, message.upload, user, message)}
          />
        ) : (
          <Empty className="flex-1">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <MicIcon />
              </EmptyMedia>
              <EmptyTitle>No messages yet</EmptyTitle>
              <EmptyDescription>Hold the button below and say something.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
        <PttButton
          disabled={!user}
          onRecordingChange={(recording) => recording && stopPlayback()}
          onRecorded={(recording) => user && void sendRecording(channelId, recording.blob, user)}
        />
      </section>
      <aside className="hidden w-60 shrink-0 border-s p-3 lg:block" aria-label="Channel members">
        <h2 className="mb-2 px-2 text-xs font-medium text-muted-foreground">
          Members · {onlineCount} online
        </h2>
        {members.data && <MemberList members={members.data} online={socket.online} />}
      </aside>
    </div>
  )
}
