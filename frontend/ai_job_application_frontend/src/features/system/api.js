import { api } from '@/api/client'

export function getHealth({ signal } = {}) {
  return api.get('/health', { signal })
}

export function getSystemStatus({ signal } = {}) {
  return api.get('/admin/system', { signal })
}
