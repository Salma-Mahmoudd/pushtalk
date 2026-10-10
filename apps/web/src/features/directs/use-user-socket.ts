import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { refreshOnce } from '@/shared/lib/api/client'
import { socketUrl, WsClient } from '@/shared/lib/ws/ws-client'

import { directKeys } from './queries'

/**
 * The app-wide socket of a logged-in user: marks them online for their conversations and
 * lists a new conversation as soon as someone starts one with them.
 */
export function useUserSocket() {
  const queryClient = useQueryClient()

  useEffect(() => {
    const socket = new WsClient({
      url: () => socketUrl('/ws/me'),
      refreshSession: refreshOnce,
      onEvent: (event) => {
        if (event.type === 'dm.created') void queryClient.invalidateQueries({ queryKey: directKeys.all })
      },
      // Anything may have changed while disconnected.
      onStateChange: (state) => state === 'open' && void queryClient.invalidateQueries({ queryKey: directKeys.all }),
    })
    socket.connect()
    return () => socket.close()
  }, [queryClient])
}
