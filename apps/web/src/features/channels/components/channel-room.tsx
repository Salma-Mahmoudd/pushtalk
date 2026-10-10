import { AtSignIcon, HashIcon, LockIcon, MicIcon } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useParams } from 'react-router'

import { useAuthStore } from '@/features/auth/store'
import { AudioUnlockBanner, HeldWhileTalkingBadge, PlayHereBanner } from '@/features/voice/components/playback-banners'
import { PttButton } from '@/features/voice/components/ptt-button'
import { SpeedControl } from '@/features/voice/components/speed-control'
import type { QueueItem } from '@/features/voice/playback-queue'
import { usePlayback } from '@/features/voice/use-playback'
import { ApiError } from '@/shared/lib/api/client'
import { Button } from '@/shared/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/shared/ui/empty'
import { Spinner } from '@/shared/ui/spinner'

import { type ChatMessage, type MessageOut, orderMessages, useMessageStore } from '../message-store'
import { useChannel, useJoinChannel, useMembers } from '../queries'
import { sendRecording } from '../send'
import { useChannelHistory } from '../use-channel-history'
import { type IncomingOptions, useChannelSocket } from '../use-channel-socket'
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

const audioSrc = (messageId: string) => `/api/messages/${messageId}/audio`

/** The page for /channels/:channelId; remounts per channel, so each room has its own queue. */
export function ChannelRoomPage() {
  const { channelId = '' } = useParams()
  return <ChannelRoom key={channelId} channelId={channelId} />
}

function ChannelRoom({ channelId }: { channelId: string }) {
  const channel = useChannel(channelId)
  const isMember = channel.isSuccess
  const members = useMembers(channelId, isMember)
  const user = useAuthStore((state) => state.user)
  const userId = user?.id

  const sendRef = useRef<(event: { type: string; data?: Record<string, unknown> }) => boolean>(() => false)
  // One event for a whole batch (a catch-up can deliver 200 messages at once).
  const report = useCallback((messageIds: string[], status: 'delivered' | 'played') => {
    if (messageIds.length > 0) sendRef.current({ type: 'receipt', data: { message_ids: messageIds, status } })
  }, [])

  const { queue, snapshot } = usePlayback(useCallback((item: QueueItem) => report([item.id], 'played'), [report]))

  const onIncoming = useCallback(
    (messages: MessageOut[], { autoplay }: IncomingOptions) => {
      const delivered: string[] = []
      for (const message of messages) {
        if (message.sender.id === userId || message.seq === null) continue
        delivered.push(message.id)
        if (autoplay) queue.enqueue({ id: message.id, seq: message.seq, src: audioSrc(message.id), own: false })
      }
      report(delivered, 'delivered')
    },
    [queue, report, userId],
  )
  const onPlaybackActive = useCallback((active: boolean) => queue.setActive(active), [queue])
  const handlers = useMemo(() => ({ onIncoming, onPlaybackActive }), [onIncoming, onPlaybackActive])

  const socket = useChannelSocket(channelId, isMember, handlers)
  useEffect(() => {
    sendRef.current = socket.send
  }, [socket.send])
  const history = useChannelHistory(channelId, isMember)
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

  // A direct conversation is titled by the other person.
  const direct = channel.data?.kind === 'direct'
  const title = direct ? channel.data?.peer?.username : channel.data?.name
  const onlineCount = members.data?.filter((member) => socket.online.has(member.id)).length ?? 0
  const play = (message: ChatMessage) =>
    message.id &&
    message.seq !== null &&
    queue.playNow({ id: message.id, seq: message.seq, src: audioSrc(message.id), own: message.sender.id === userId })

  return (
    <div className="flex min-h-0 flex-1">
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b px-4 py-3">
          {direct ? <AtSignIcon className="size-4 text-muted-foreground" /> : <HashIcon className="size-4 text-muted-foreground" />}
          <h1 className="truncate font-semibold">{title}</h1>
          <div className="ms-auto flex items-center gap-3">
            <SpeedControl />
            <ConnectionStatus state={socket.state} />
          </div>
        </header>
        <AudioUnlockBanner snapshot={snapshot} />
        <PlayHereBanner snapshot={snapshot} onPlayHere={socket.claimPlayback} />
        {messages.length > 0 ? (
          <MessageList
            messages={messages}
            currentUserId={userId}
            playingId={snapshot.currentId}
            onPlay={play}
            onStop={() => queue.stopCurrent()}
            onRetry={(message) => message.upload && user && void sendRecording(channelId, message.upload, user, message)}
            header={
              history.hasOlder && (
                <div className="mb-3 flex justify-center">
                  <Button variant="ghost" size="sm" disabled={history.loadingOlder} onClick={history.loadOlder}>
                    {history.loadingOlder && <Spinner />}
                    Load older messages
                  </Button>
                </div>
              )
            }
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
        <HeldWhileTalkingBadge snapshot={snapshot} />
        <PttButton
          disabled={!user}
          onRecordingChange={(recording) => (recording ? queue.recordingStarted() : queue.recordingStopped())}
          onRecorded={(recording) => user && void sendRecording(channelId, recording.blob, user)}
        />
      </section>
      <aside className="hidden w-60 shrink-0 border-s p-3 lg:block" aria-label="Channel members">
        <h2 className="mb-2 px-2 text-xs font-medium text-muted-foreground">Members · {onlineCount} online</h2>
        {members.data && <MemberList members={members.data} online={socket.online} />}
      </aside>
    </div>
  )
}
