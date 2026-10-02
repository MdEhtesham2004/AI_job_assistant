const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'medium',
})

/** 20480 → "20 KB", 3500000 → "3.3 MB"; '' when empty. */
export function formatBytes(bytes) {
  if (!bytes) return ''
  return bytes < 1024 * 1024
    ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / 1048576).toFixed(1)} MB`
}

/** Format an ISO string, Date or epoch milliseconds for display; returns '—' when empty. */
export function formatDateTime(value) {
  if (value === null || value === undefined || value === '') return '—'
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateTimeFormatter.format(date)
}
