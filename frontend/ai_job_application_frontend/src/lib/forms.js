import { ApiError } from '@/api/client'

/**
 * Show an API error on a react-hook-form form (Phase 1 §4):
 * 422 field errors go under their fields; everything else becomes a form-level message.
 */
export function applyServerErrors(error, setError, fieldNames = []) {
  if (error instanceof ApiError && error.code === 'VALIDATION_ERROR') {
    let placed = false
    for (const field of error.details?.fields ?? []) {
      const name = field.loc?.[field.loc.length - 1]
      if (fieldNames.includes(name)) {
        setError(name, { type: 'server', message: field.message })
        placed = true
      }
    }
    if (placed) return
  }
  setError('root.server', {
    type: 'server',
    message: error instanceof ApiError ? error.message : 'Something went wrong. Please try again.',
  })
}
