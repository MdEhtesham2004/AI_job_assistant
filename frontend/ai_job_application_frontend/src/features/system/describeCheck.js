const LABELS = { api: 'Backend API', database: 'Database' }

/**
 * Turn one entry of `health.checks` into what a ServiceRow shows.
 * Returns { name, status: healthy|degraded|unreachable, statusLabel, detail }.
 */
export function describeCheck(key, check, health) {
  const name = LABELS[key] ?? key
  const details = check?.details ?? {}

  if (check?.status !== 'ok') {
    return {
      name,
      status: 'unreachable',
      statusLabel: 'unreachable',
      detail: details.error ?? 'Check failed',
    }
  }

  if (key === 'api') {
    return {
      name,
      status: 'healthy',
      statusLabel: 'healthy',
      detail: `v${health.version} · ${health.environment}`,
    }
  }

  if (key === 'database') {
    const parts = [
      details.revision ? `revision ${details.revision}` : 'no migrations applied',
      `${details.tables ?? 0} tables`,
      details.latency_ms !== undefined ? `${details.latency_ms} ms` : null,
    ].filter(Boolean)

    if (!details.up_to_date) {
      return {
        name,
        status: 'degraded',
        statusLabel: 'migration pending',
        detail: `${parts.join(' · ')} · expected ${details.head ?? 'unknown'}`,
      }
    }
    return { name, status: 'healthy', statusLabel: 'connected', detail: parts.join(' · ') }
  }

  return { name, status: 'healthy', statusLabel: 'healthy', detail: undefined }
}
