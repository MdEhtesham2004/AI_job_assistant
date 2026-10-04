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

const relativeFormatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
const RELATIVE_STEPS = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

/** "3 days ago", "in 2 hours", "now"; '—' when empty. */
export function formatRelative(value, now = Date.now()) {
  if (value === null || value === undefined || value === '') return '—'
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return '—'
  const seconds = Math.round((time - now) / 1000)
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(seconds) >= size) return relativeFormatter.format(Math.round(seconds / size), unit)
  }
  return relativeFormatter.format(0, 'second')
}

/** Format an ISO string, Date or epoch milliseconds for display; returns '—' when empty. */
export function formatDateTime(value) {
  if (value === null || value === undefined || value === '') return '—'
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateTimeFormatter.format(date)
}

const dateFormatter = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })

/** "1 Nov": a day without the time; '—' when empty. */
export function formatDate(value) {
  if (value === null || value === undefined || value === '') return '—'
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateFormatter.format(date)
}
