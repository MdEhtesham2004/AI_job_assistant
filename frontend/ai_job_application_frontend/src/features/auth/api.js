import { api, refreshSession } from '@/api/client'

export const authApi = {
  register: (values) => api.post('/auth/register', values),
  login: (values) => api.post('/auth/login', values),
  logout: () => api.post('/auth/logout'),
  refresh: () => refreshSession(),
  me: () => api.get('/users/me'),
  changePassword: (values) => api.post('/auth/change-password', values),
}
