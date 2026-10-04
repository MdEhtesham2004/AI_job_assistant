import { api } from '@/api/client'

export const notificationsApi = {
  list: () => api.get('/notifications?page_size=10'),
  /** Notification centre: { unread_only, category, page } */
  page: ({ unreadOnly = false, category = '', page = 1 } = {}) => {
    const search = new URLSearchParams({ page: String(page), page_size: '30' })
    if (unreadOnly) search.set('unread_only', 'true')
    if (category) search.set('category', category)
    return api.get(`/notifications?${search}`)
  },
  unreadCount: () => api.get('/notifications/unread-count'),
  markRead: (id) => api.post(`/notifications/${id}/read`),
  markAllRead: () => api.post('/notifications/read-all'),
}
