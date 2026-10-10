import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { channelsApi } from './api'

export const channelKeys = {
  all: ['channels'] as const,
  detail: (channelId: string) => ['channels', channelId] as const,
  members: (channelId: string) => ['channels', channelId, 'members'] as const,
}

export function useChannels() {
  return useQuery({ queryKey: channelKeys.all, queryFn: channelsApi.list })
}

export function useChannel(channelId: string) {
  return useQuery({ queryKey: channelKeys.detail(channelId), queryFn: () => channelsApi.get(channelId) })
}

export function useMembers(channelId: string, enabled = true) {
  return useQuery({
    queryKey: channelKeys.members(channelId),
    queryFn: () => channelsApi.members(channelId),
    enabled,
  })
}

export function useCreateChannel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: channelsApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: channelKeys.all }),
  })
}

export function useJoinChannel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: channelsApi.join,
    onSuccess: (_, channelId) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: channelKeys.all, exact: true }),
        queryClient.invalidateQueries({ queryKey: channelKeys.detail(channelId) }),
      ]),
  })
}
