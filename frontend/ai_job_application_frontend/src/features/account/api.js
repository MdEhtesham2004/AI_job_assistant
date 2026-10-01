import { api } from '@/api/client'

export const accountApi = {
  updateName: (full_name) => api.patch('/users/me', { full_name }),
  getProfile: () => api.get('/users/me/profile'),
  updateProfile: (profile) => api.put('/users/me/profile', profile),
  getSettings: () => api.get('/users/me/settings'),
  updateSettings: (changes) => api.patch('/users/me/settings', changes),
}
