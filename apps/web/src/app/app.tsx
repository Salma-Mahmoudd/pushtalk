import { useEffect } from 'react'
import { RouterProvider } from 'react-router'

import { restoreSession, startSessionSync } from '@/features/auth/session'

import { router } from './router'

export function App() {
  useEffect(() => {
    const stop = startSessionSync()
    void restoreSession()
    return stop
  }, [])

  return <RouterProvider router={router} />
}
