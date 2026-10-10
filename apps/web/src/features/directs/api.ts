import { apiRequest } from '@/shared/lib/api/client'
import type { components } from '@/shared/lib/api/schema'

export type Direct = components['schemas']['DirectOut']
export type User = components['schemas']['UserOut']

export const directsApi = {
  list: () => apiRequest<Direct[]>('/api/dms'),
  open: (userId: string) => apiRequest<Direct>('/api/dms', { method: 'POST', body: { user_id: userId } }),
  searchUsers: (query: string) => apiRequest<User[]>(`/api/users?query=${encodeURIComponent(query)}`),
}
