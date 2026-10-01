import { api } from '@/api/client'

export function getHealth({ signal } = {}) {
  return api.get('/health', { signal })
}
