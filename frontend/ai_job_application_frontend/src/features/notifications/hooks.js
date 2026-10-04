import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { queryKeys } from '@/api/queryKeys'

import { notificationsApi } from './api'

export function useUnreadCount() {
  return useQuery({
    queryKey: queryKeys.notifications.unread(),
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 30_000,
  })
}

export function useNotificationList({ enabled }) {
  return useQuery({
    queryKey: queryKeys.notifications.list(),
    queryFn: notificationsApi.list,
    enabled,
  })
}

export function useNotificationPage(filters) {
  return useQuery({
    queryKey: [...queryKeys.notifications.all(), 'page', filters],
    queryFn: () => notificationsApi.page(filters),
    placeholderData: keepPreviousData,
  })
}

export function useMarkRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id) => notificationsApi.markRead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all() }),
  })
}

export function useMarkAllRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all() }),
  })
}
