import { useEffect } from 'react'

import { apiRequest } from '@/shared/lib/api/client'
import type { components } from '@/shared/lib/api/schema'
import type { SocketState } from '@/shared/lib/ws/ws-client'

import { fromServer, useMessageStore } from './message-store'

type MessagePage = components['schemas']['MessagePage']

/** Loads the newest messages when the room opens and again after every reconnect. */
export function useChannelHistory(channelId: string, socketState: SocketState, enabled: boolean): void {
  useEffect(() => {
    if (!enabled || socketState !== 'open') return
    const controller = new AbortController()
    apiRequest<MessagePage>(`/api/channels/${channelId}/messages`, { signal: controller.signal })
      .then((page) => useMessageStore.getState().upsert([...page.messages, ...page.pending].map(fromServer)))
      .catch(() => undefined) // The next reconnect loads again.
    return () => controller.abort()
  }, [channelId, socketState, enabled])
}
