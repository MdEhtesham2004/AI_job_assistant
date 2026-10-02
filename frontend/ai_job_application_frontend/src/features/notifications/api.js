import { api } from '@/api/client'

export const notificationsApi = {
  list: () => api.get('/notifications?page_size=10'),
  unreadCount: () => api.get('/notifications/unread-count'),
  markRead: (id) => api.post(`/notifications/${id}/read`),
  markAllRead: () => api.post('/notifications/read-all'),
}
