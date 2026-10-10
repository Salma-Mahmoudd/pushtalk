import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { directsApi } from './api'

export const directKeys = {
  all: ['dms'] as const,
  search: (query: string) => ['users', query] as const,
}

/** The user's conversations; the online dots refresh every 30 s and on dm.created. */
export function useDirects() {
  return useQuery({ queryKey: directKeys.all, queryFn: directsApi.list, refetchInterval: 30_000 })
}

export function useUserSearch(query: string) {
  return useQuery({
    queryKey: directKeys.search(query),
    queryFn: () => directsApi.searchUsers(query),
    enabled: query.length > 0,
    staleTime: 30_000,
  })
}

export function useOpenDirect() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: directsApi.open,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: directKeys.all }),
  })
}
