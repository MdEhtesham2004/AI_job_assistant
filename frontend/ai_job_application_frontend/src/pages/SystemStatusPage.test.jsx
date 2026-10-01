import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, renderWithProviders } from '@/test/utils'

import SystemStatusPage from './SystemStatusPage'

const databaseOk = {
  status: 'ok',
  details: { revision: '0001', head: '0001', up_to_date: true, tables: 3, latency_ms: 1.5 },
}

function health(overrides = {}) {
  return {
    status: 'ok',
    service: 'AI Job Application Platform',
    version: '0.1.0',
    environment: 'development',
    timestamp: '2026-10-01T10:00:00Z',
    checks: { api: { status: 'ok', details: {} }, database: databaseOk },
    ...overrides,
  }
}

function mockHealth(body) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body)))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SystemStatusPage', () => {
  it('shows the backend and the database as healthy', async () => {
    mockHealth(health())

    renderWithProviders(<SystemStatusPage />)

    // Wait for loaded data ("Backend API" is also shown on the loading row).
    expect(await screen.findByText('connected')).toBeInTheDocument()
    expect(screen.getByText('Backend API')).toBeInTheDocument()
    expect(screen.getByText('v0.1.0 · development')).toBeInTheDocument()
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.getByText('revision 0001 · 3 tables · 1.5 ms')).toBeInTheDocument()
  })

  it('shows the database as unreachable when its check fails', async () => {
    mockHealth(
      health({
        status: 'degraded',
        checks: {
          api: { status: 'ok', details: {} },
          database: { status: 'error', details: { error: 'Database unreachable' } },
        },
      }),
    )

    renderWithProviders(<SystemStatusPage />)

    expect(await screen.findByText('unreachable')).toBeInTheDocument()
    expect(screen.getByText('Database unreachable')).toBeInTheDocument()
    expect(screen.getByText('healthy')).toBeInTheDocument() // the API itself is still fine
  })

  it('warns when migrations are not applied', async () => {
    mockHealth(
      health({
        checks: {
          api: { status: 'ok', details: {} },
          database: {
            status: 'ok',
            details: { revision: null, head: '0001', up_to_date: false, tables: 0, latency_ms: 2 },
          },
        },
      }),
    )

    renderWithProviders(<SystemStatusPage />)

    expect(await screen.findByText('migration pending')).toBeInTheDocument()
    expect(
      screen.getByText('no migrations applied · 0 tables · 2 ms · expected 0001'),
    ).toBeInTheDocument()
  })

  it('shows the backend as unreachable when the API cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderWithProviders(<SystemStatusPage />)

    expect(await screen.findByText('unreachable')).toBeInTheDocument()
    expect(screen.getByText('Cannot reach the server.')).toBeInTheDocument()
  })
})
