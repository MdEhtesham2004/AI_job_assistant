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
  resumes: {
    all: () => ['resumes'],
    overview: () => ['resumes', 'overview'],
    version: (id) => ['resumes', 'version', id],
  },
  jobs: {
    all: () => ['jobs'],
    lists: () => ['jobs', 'list'],
    list: (filters) => ['jobs', 'list', filters],
    counts: () => ['jobs', 'counts'],
    detail: (id) => ['jobs', 'detail', id],
    searches: () => ['jobs', 'searches'],
    // Not under 'searches': refreshing the recent list must not refetch every run (loop).
    searchRun: (id) => ['jobs', 'search-run', id],
    suggestedRoles: () => ['jobs', 'suggested-roles'],
    saved: () => ['jobs', 'saved'],
    analysisSummary: (filters) => ['jobs', 'analysis-summary', filters],
    documents: (id) => ['jobs', 'documents', id],
  },
  applications: {
    all: () => ['applications'],
    list: (filters) => ['applications', 'list', filters],
    counts: () => ['applications', 'counts'],
    detail: (id) => ['applications', 'detail', id],
    forJob: (jobId) => ['applications', 'for-job', jobId],
  },
  gmail: {
    status: () => ['gmail', 'status'],
  },
  contacts: {
    all: () => ['contacts'],
    list: (filters) => ['contacts', 'list', filters],
    counts: () => ['contacts', 'counts'],
    blocked: () => ['contacts', 'blocked'],
  },
  emails: {
    all: () => ['emails'],
    outbox: (filters) => ['emails', 'outbox', filters],
    summary: () => ['emails', 'summary'],
    forApplication: (id) => ['emails', 'application', id],
    replies: (id) => ['emails', 'replies', id],
  },
  dashboard: {
    summary: () => ['dashboard', 'summary'],
  },
  usage: () => ['usage'],
  admin_insights: {
    audit: (filters) => ['admin-insights', 'audit', filters],
    analytics: () => ['admin-insights', 'analytics'],
    errors: () => ['admin-insights', 'errors'],
  },
  automation: {
    status: () => ['automation', 'status'],
    platform: () => ['automation', 'platform'],
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
