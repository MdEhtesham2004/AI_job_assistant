import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeAuth, makeUser, mockApi, renderWithProviders } from '@/test/utils'

import SystemStatusPage from './SystemStatusPage'

const ok = (details = {}) => ({ status: 'ok', details })

function systemStatus(overrides = {}) {
  return {
    status: 'ok',
    checked_at: '2026-10-02T10:00:00Z',
    services: {
      api: ok({ version: '0.1.0' }),
      database: ok({ revision: '0004', head: '0004', up_to_date: true, tables: 8, latency_ms: 2 }),
      redis: ok({ latency_ms: 1 }),
      worker: ok({ workers: ['celery@pc'], latency_ms: 30 }),
      storage: ok({ backend: 'local', latency_ms: 3 }),
      gotenberg: ok({ latency_ms: 40 }),
      ai: ok({ model: 'openai/gpt-oss-120b' }),
      ...overrides,
    },
    tasks: { queued: 0, running: 1, succeeded: 5, failed: 2, cancelled: 0 },
  }
}

const admin = makeAuth({ user: makeUser({ role: 'admin' }) })

afterEach(() => vi.unstubAllGlobals())

describe('SystemStatusPage', () => {
  it('lists every service with its details', async () => {
    mockApi({ 'GET /admin/system': systemStatus() })

    renderWithProviders(<SystemStatusPage />, { auth: admin })

    expect(await screen.findByText('Background worker')).toBeInTheDocument()
    expect(screen.getByText('revision 0004 · 8 tables · 2 ms')).toBeInTheDocument()
    expect(screen.getByText('1 worker(s) · 30 ms')).toBeInTheDocument()
    expect(screen.getByText('openai/gpt-oss-120b')).toBeInTheDocument()
    expect(screen.getByText(/queued 0 · running 1 · done 5 · failed 2/)).toBeInTheDocument()
  })

  it('shows broken and unconfigured services', async () => {
    mockApi({
      'GET /admin/system': systemStatus({
        worker: { status: 'error', details: { error: 'RuntimeError' } },
        ai: { status: 'not_configured', details: {} },
      }),
    })

    renderWithProviders(<SystemStatusPage />, { auth: admin })

    expect(await screen.findByText('unreachable')).toBeInTheDocument()
    expect(screen.getByText('not configured')).toBeInTheDocument()
  })

  it('runs a diagnostic task and shows its progress', async () => {
    const fetchMock = mockApi({
      'GET /admin/system': systemStatus(),
      'POST /tasks/test-pdf': { task_id: 't-1' },
      'GET /tasks/t-1': {
        id: 't-1',
        type: 'test_pdf',
        status: 'succeeded',
        progress: 100,
        attempts: 1,
        result: {
          file: {
            name: 'test.pdf',
            size: 19000,
            content_type: 'application/pdf',
            download_url: '/api/v1/files/x',
          },
        },
        error: null,
        created_at: '2026-10-02T10:00:00Z',
        started_at: null,
        finished_at: null,
      },
    })
    renderWithProviders(<SystemStatusPage />, { auth: admin })

    const run = await screen.findAllByRole('button', { name: 'Run' })
    await userEvent.click(run[0])

    expect(await screen.findByRole('link', { name: /test\.pdf/ })).toHaveAttribute(
      'href',
      '/api/v1/files/x',
    )
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => url.endsWith('/tasks/test-pdf') && init.method === 'POST',
      ),
    ).toBe(true)
  })
})
