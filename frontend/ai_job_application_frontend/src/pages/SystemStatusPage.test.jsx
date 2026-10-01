import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, renderWithProviders } from '@/test/utils'

import SystemStatusPage from './SystemStatusPage'

const healthy = {
  status: 'ok',
  service: 'AI Job Application Platform',
  version: '0.1.0',
  environment: 'development',
  timestamp: '2026-10-01T10:00:00Z',
  checks: { api: 'ok' },
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SystemStatusPage', () => {
  it('shows the backend as healthy with its version', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(healthy)))

    renderWithProviders(<SystemStatusPage />)

    expect(await screen.findByText('healthy')).toBeInTheDocument()
    expect(screen.getByText('Backend API')).toBeInTheDocument()
    expect(screen.getByText('v0.1.0 · development')).toBeInTheDocument()
  })

  it('shows unreachable when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderWithProviders(<SystemStatusPage />)

    expect(await screen.findByText('unreachable')).toBeInTheDocument()
    expect(screen.getByText('Cannot reach the server.')).toBeInTheDocument()
  })

  it('lists every dependency check the backend reports', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(jsonResponse({ ...healthy, checks: { api: 'ok', database: 'ok' } })),
    )

    renderWithProviders(<SystemStatusPage />)

    expect(await screen.findByText('database')).toBeInTheDocument()
    expect(screen.getAllByText('healthy')).toHaveLength(2)
  })
})
