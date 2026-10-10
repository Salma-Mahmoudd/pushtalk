import { Navigate, Outlet, useLocation } from 'react-router'

import { Spinner } from '@/shared/ui/spinner'

import { useAuthStore } from '../store'

function Checking() {
  return (
    <div className="grid min-h-svh place-items-center" aria-busy="true">
      <Spinner className="size-6" />
    </div>
  )
}

/** Pages that need a session; others are sent to /login and brought back afterwards. */
export function RequireAuth() {
  const status = useAuthStore((state) => state.status)
  const location = useLocation()
  if (status === 'unknown') return <Checking />
  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
  }
  return <Outlet />
}

/** Log-in and sign-up pages; a logged-in user goes on to where they were heading. */
export function GuestOnly() {
  const status = useAuthStore((state) => state.status)
  const location = useLocation()
  if (status === 'unknown') return <Checking />
  if (status === 'authenticated') {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from ?? '/channels'} replace />
  }
  return <Outlet />
}
