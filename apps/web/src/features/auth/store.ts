import { create } from 'zustand'

import type { Session, User } from './api'

/** unknown: not checked yet (app start); anonymous: logged out; authenticated: logged in. */
export type AuthStatus = 'unknown' | 'anonymous' | 'authenticated'

interface AuthState {
  status: AuthStatus
  user: User | null
  /** When the access cookie expires (ms since epoch); the token itself is never readable. */
  accessExpiresAt: number | null
  setSession: (session: Session) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  status: 'unknown',
  user: null,
  accessExpiresAt: null,
  setSession: (session) =>
    set({ status: 'authenticated', user: session.user, accessExpiresAt: Date.parse(session.access_expires_at) }),
  clear: () => set({ status: 'anonymous', user: null, accessExpiresAt: null }),
}))
