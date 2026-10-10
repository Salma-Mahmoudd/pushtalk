import { useCallback, useEffect, useState } from 'react'

import { apiRequest } from '@/shared/lib/api/client'
import type { components } from '@/shared/lib/api/schema'

import { firstSeq, fromServer, useMessageStore } from './message-store'

type MessagePage = components['schemas']['MessagePage']

export interface ChannelHistory {
  hasOlder: boolean
  loadingOlder: boolean
  loadOlder: () => void
}

/** The newest page when the room opens (later messages arrive by WebSocket), and older pages on request. */
export function useChannelHistory(channelId: string, enabled: boolean): ChannelHistory {
  const [hasOlder, setHasOlder] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    apiRequest<MessagePage>(`/api/channels/${channelId}/messages`, { signal: controller.signal })
      .then((page) => {
        useMessageStore.getState().upsert([...page.messages, ...page.pending].map(fromServer))
        setHasOlder(page.has_more)
      })
      .catch(() => undefined) // Shown as empty; the socket's catch-up still delivers new messages.
    return () => controller.abort()
  }, [channelId, enabled])

  const loadOlder = useCallback(() => {
    const before = firstSeq(channelId)
    if (before === null) return
    setLoadingOlder(true)
    apiRequest<MessagePage>(`/api/channels/${channelId}/messages?before_seq=${before}`)
      .then((page) => {
        useMessageStore.getState().upsert(page.messages.map(fromServer))
        setHasOlder(page.has_more)
      })
      .catch(() => undefined)
      .finally(() => setLoadingOlder(false))
  }, [channelId])

  return { hasOlder, loadingOlder, loadOlder }
}
