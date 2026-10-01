/** Central TanStack Query keys — one namespace per feature. */
export const queryKeys = {
  system: {
    health: () => ['system', 'health'],
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
}
