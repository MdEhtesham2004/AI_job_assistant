import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'

import { adminApi } from './api'

export function useAdminUsers(filters) {
  return useQuery({
    queryKey: queryKeys.admin.users(filters),
    queryFn: () => adminApi.listUsers(filters),
    placeholderData: keepPreviousData,
  })
}

export function useUserCounts({ enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.admin.userCounts(),
    queryFn: adminApi.userCounts,
    enabled,
    refetchInterval: 60_000,
  })
}

const ACTIONS = {
  approve: { run: ({ id }) => adminApi.approve(id), done: (u) => `${u.full_name} approved.` },
  reject: {
    run: ({ id, reason }) => adminApi.reject(id, reason),
    done: (u) => `${u.full_name} rejected.`,
  },
  deactivate: {
    run: ({ id }) => adminApi.deactivate(id),
    done: (u) => `${u.full_name} deactivated.`,
  },
  reactivate: {
    run: ({ id }) => adminApi.reactivate(id),
    done: (u) => `${u.full_name} reactivated.`,
  },
  makeAdmin: {
    run: ({ id }) => adminApi.changeRole(id, 'admin'),
    done: (u) => `${u.full_name} is now an admin.`,
  },
  removeAdmin: {
    run: ({ id }) => adminApi.changeRole(id, 'user'),
    done: (u) => `${u.full_name} is no longer an admin.`,
  },
}

/** One mutation for every row action; refreshes the list and the tab counts. */
export function useUserAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ action, ...args }) => ACTIONS[action].run(args),
    onSuccess: (user, { action }) => {
      toast.success(ACTIONS[action].done(user))
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.usersAll() })
    },
    onError: (error) => toast.error(error.message),
  })
}
