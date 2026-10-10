import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { RouterProvider } from 'react-router'

import { restoreSession, startSessionSync } from '@/features/auth/session'
import { useAuthStore } from '@/features/auth/store'
import { ApiError } from '@/shared/lib/api/client'
import { TooltipProvider } from '@/shared/ui/tooltip'

import { router } from './router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Client errors (403, 404 …) will not change on retry; server and network errors may.
      retry: (failures, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failures < 2,
    },
  },
})

export function App() {
  useEffect(() => {
    const stop = startSessionSync()
    // Cached data belongs to the session: drop it when the session ends.
    const unsubscribe = useAuthStore.subscribe((state, previous) => {
      if (state.status === 'anonymous' && previous.status === 'authenticated') queryClient.clear()
    })
    void restoreSession()
    return () => {
      unsubscribe()
      stop()
    }
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
