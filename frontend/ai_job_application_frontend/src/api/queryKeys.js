/** Central TanStack Query keys — one namespace per feature. */
export const queryKeys = {
  system: {
    health: () => ['system', 'health'],
    admin: () => ['system', 'admin'],
  },
  account: {
    profile: () => ['account', 'profile'],
    settings: () => ['account', 'settings'],
  },
  admin: {
    users: (filters) => ['admin', 'users', 'list', filters],
    usersAll: () => ['admin', 'users'],
    userCounts: () => ['admin', 'users', 'counts'],
  },
  tasks: {
    all: () => ['tasks'],
    list: (page) => ['tasks', 'list', page],
    detail: (id) => ['tasks', 'detail', id],
  },
  notifications: {
    all: () => ['notifications'],
    list: () => ['notifications', 'list'],
    unread: () => ['notifications', 'unread'],
  },
}
