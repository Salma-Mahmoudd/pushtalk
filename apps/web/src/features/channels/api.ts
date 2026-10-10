import { apiRequest } from '@/shared/lib/api/client'
import type { components } from '@/shared/lib/api/schema'

export type Channel = components['schemas']['ChannelOut']
export type Member = components['schemas']['MemberOut']

export const channelsApi = {
  list: () => apiRequest<Channel[]>('/api/channels'),
  create: (name: string) => apiRequest<Channel>('/api/channels', { method: 'POST', body: { name } }),
  get: (channelId: string) => apiRequest<Channel>(`/api/channels/${channelId}`),
  join: (channelId: string) => apiRequest<void>(`/api/channels/${channelId}/join`, { method: 'POST' }),
  members: (channelId: string) => apiRequest<Member[]>(`/api/channels/${channelId}/members`),
}
