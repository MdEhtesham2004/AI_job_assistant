import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { queryKeys } from '@/api/queryKeys'

import { accountApi } from './api'

export function useProfile() {
  return useQuery({ queryKey: queryKeys.account.profile(), queryFn: accountApi.getProfile })
}

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: accountApi.updateProfile,
    onSuccess: (profile) => queryClient.setQueryData(queryKeys.account.profile(), profile),
  })
}

export function useSettings() {
  return useQuery({ queryKey: queryKeys.account.settings(), queryFn: accountApi.getSettings })
}

export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: accountApi.updateSettings,
    onSuccess: (settings) => queryClient.setQueryData(queryKeys.account.settings(), settings),
  })
}
