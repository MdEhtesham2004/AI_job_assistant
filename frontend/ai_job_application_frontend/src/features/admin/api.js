import { api } from '@/api/client'

function toQuery(params) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const adminApi = {
  listUsers: ({ status, q, page, page_size }) =>
    api.get(`/admin/users${toQuery({ status, q, page, page_size })}`),
  userCounts: () => api.get('/admin/users/counts'),
  approve: (id) => api.post(`/admin/users/${id}/approve`),
  reject: (id, reason) => api.post(`/admin/users/${id}/reject`, { reason: reason || null }),
  deactivate: (id) => api.post(`/admin/users/${id}/deactivate`),
  reactivate: (id) => api.post(`/admin/users/${id}/reactivate`),
  changeRole: (id, role) => api.patch(`/admin/users/${id}/role`, { role }),
}
