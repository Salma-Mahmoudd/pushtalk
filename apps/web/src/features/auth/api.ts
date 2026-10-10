import { apiRequest } from '@/shared/lib/api/client'
import type { components } from '@/shared/lib/api/schema'

export type User = components['schemas']['UserOut']
export type Session = components['schemas']['SessionOut']
export type Credentials = components['schemas']['SignupIn']

export const authApi = {
  signup: (credentials: Credentials) =>
    apiRequest<Session>('/api/auth/signup', { method: 'POST', body: credentials }),
  login: (credentials: Credentials) =>
    apiRequest<Session>('/api/auth/login', { method: 'POST', body: credentials }),
  refresh: () => apiRequest<Session>('/api/auth/refresh', { method: 'POST' }),
  logout: () => apiRequest<void>('/api/auth/logout', { method: 'POST' }),
  me: () => apiRequest<Session>('/api/auth/me'),
}
