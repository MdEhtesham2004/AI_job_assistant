const LABELS = {
  api: 'Backend API',
  database: 'Database',
  redis: 'Redis (queue & cache)',
  worker: 'Background worker',
  storage: 'File storage',
  gotenberg: 'PDF service (Gotenberg)',
  ai: 'AI provider',
  scheduler: 'Scheduler (saved searches)',
  jsearch: 'Job search (JSearch)',
}

export const SERVICE_ORDER = Object.keys(LABELS)

const ms = (details) => (details.latency_ms !== undefined ? `${details.latency_ms} ms` : null)

/**
 * Turn one entry of `system.services` into what a ServiceRow shows.
 * Returns { name, status: healthy|degraded|unreachable|checking, statusLabel, detail }.
 */
export function describeCheck(key, check) {
  const name = LABELS[key] ?? key
  const details = check?.details ?? {}

  if (check?.status === 'disabled') {
    return { name, status: 'checking', statusLabel: 'disabled', detail: 'Turned off in settings' }
  }
  if (check?.status === 'not_configured') {
    return { name, status: 'degraded', statusLabel: 'not configured', detail: 'No API key set' }
  }
  if (check?.status === 'error' && key === 'scheduler') {
    return {
      name,
      status: 'unreachable',
      statusLabel: 'not running',
      detail: 'Start Celery Beat — saved searches will not run on schedule',
    }
  }
  if (check?.status !== 'ok') {
    return {
      name,
      status: 'unreachable',
      statusLabel: 'unreachable',
      detail: details.error ?? 'Check failed',
    }
  }

  const join = (...parts) => parts.filter(Boolean).join(' · ') || undefined
  switch (key) {
    case 'api':
      return { name, status: 'healthy', statusLabel: 'healthy', detail: `v${details.version}` }
    case 'database': {
      const base = join(
        details.revision ? `revision ${details.revision}` : 'no migrations applied',
        `${details.tables ?? 0} tables`,
        ms(details),
      )
      return details.up_to_date
        ? { name, status: 'healthy', statusLabel: 'connected', detail: base }
        : {
            name,
            status: 'degraded',
            statusLabel: 'migration pending',
            detail: `${base} · expected ${details.head ?? 'unknown'}`,
          }
    }
    case 'worker':
      return {
        name,
        status: 'healthy',
        statusLabel: 'running',
        detail: join(`${details.workers?.length ?? 0} worker(s)`, ms(details)),
      }
    case 'storage':
      return {
        name,
        status: 'healthy',
        statusLabel: 'healthy',
        detail: join(details.backend, ms(details)),
      }
    case 'ai':
      return { name, status: 'healthy', statusLabel: 'configured', detail: details.model }
    case 'jsearch':
      return {
        name,
        status: 'healthy',
        statusLabel: 'configured',
        detail: join(details.endpoint, details.country && `country ${details.country}`),
      }
    case 'scheduler':
      return {
        name,
        status: 'healthy',
        statusLabel: 'running',
        detail: details.last_tick
          ? `last check ${new Date(details.last_tick).toLocaleTimeString()}`
          : undefined,
      }
    default:
      return { name, status: 'healthy', statusLabel: 'healthy', detail: ms(details) ?? undefined }
  }
}
