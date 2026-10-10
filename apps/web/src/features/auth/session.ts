import { ApiError, configureSession } from '@/shared/lib/api/client'

import { authApi, type Session } from './api'
import { useAuthStore } from './store'

/** Refresh this long before the access cookie expires, so requests never see the expiry. */
const REFRESH_LEAD_MS = 60_000

type SyncMessage = { type: 'session'; session: Session } | { type: 'logout' }

// Tabs share cookies, so they share the session: one tab's login, refresh or logout applies to all.
const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('pushtalk-auth')

function applySession(session: Session, broadcast = true): void {
  useAuthStore.getState().setSession(session)
  if (broadcast) channel?.postMessage({ type: 'session', session } satisfies SyncMessage)
}

function endSession(broadcast = true): void {
  useAuthStore.getState().clear()
  if (broadcast) channel?.postMessage({ type: 'logout' } satisfies SyncMessage)
}

/** Called after a successful login or signup. */
export function startSession(session: Session): void {
  applySession(session)
}

/**
 * Renews the session cookies. Tabs take turns through a Web Lock, so the refresh token is
 * rotated once; a tab that waited reuses the result another tab already shared.
 * Resolves false when the session is over; network errors are thrown, not treated as logout.
 */
export async function refreshSession(): Promise<boolean> {
  const seenExpiry = useAuthStore.getState().accessExpiresAt
  const run = async (): Promise<boolean> => {
    const { accessExpiresAt } = useAuthStore.getState()
    if (accessExpiresAt !== seenExpiry && accessExpiresAt !== null && accessExpiresAt - Date.now() > REFRESH_LEAD_MS) {
      return true
    }
    try {
      applySession(await authApi.refresh())
      return true
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        endSession()
        return false
      }
      throw error
    }
  }
  return 'locks' in navigator ? navigator.locks.request('pt-refresh', run) : run()
}

/** Checks the cookies at start-up: logged in, or not. */
export async function restoreSession(): Promise<void> {
  try {
    applySession(await authApi.me(), false)
  } catch {
    endSession(false)
  }
}

export async function logout(): Promise<void> {
  try {
    await authApi.logout()
  } finally {
    endSession()
  }
}

/** Wires refresh into the API client, keeps tabs in sync and refreshes before expiry. */
export function startSessionSync(): () => void {
  configureSession({ refresh: refreshSession, onSessionLost: () => endSession() })

  const onMessage = (event: MessageEvent<SyncMessage>) => {
    if (event.data.type === 'session') applySession(event.data.session, false)
    else endSession(false)
  }
  channel?.addEventListener('message', onMessage)

  let timer: ReturnType<typeof setTimeout> | undefined
  const schedule = (expiresAt: number | null) => {
    clearTimeout(timer)
    if (expiresAt === null) return
    timer = setTimeout(() => void refreshSession().catch(() => undefined), Math.max(0, expiresAt - Date.now() - REFRESH_LEAD_MS))
  }
  schedule(useAuthStore.getState().accessExpiresAt)
  const unsubscribe = useAuthStore.subscribe((state, previous) => {
    if (state.accessExpiresAt !== previous.accessExpiresAt) schedule(state.accessExpiresAt)
  })

  return () => {
    clearTimeout(timer)
    unsubscribe()
    channel?.removeEventListener('message', onMessage)
  }
}
