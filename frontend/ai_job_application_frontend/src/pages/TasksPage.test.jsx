import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockApi, renderWithProviders } from '@/test/utils'

import TasksPage from './TasksPage'

function task(overrides) {
  return {
    id: 't',
    type: 'test_pdf',
    status: 'succeeded',
    progress: 100,
    attempts: 1,
    result: null,
    error: null,
    created_at: '2026-10-02T10:00:00Z',
    started_at: null,
    finished_at: null,
    ...overrides,
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('TasksPage', () => {
  it('shows finished files, running progress and failures', async () => {
    mockApi({
      'GET /tasks': {
        items: [
          task({
            id: 'a',
            result: {
              file: {
                name: 'test.pdf',
                size: 20480,
                content_type: 'application/pdf',
                download_url: '/api/v1/files/tok',
              },
            },
          }),
          task({ id: 'b', status: 'running', progress: 40 }),
          task({
            id: 'c',
            type: 'test_failure',
            status: 'failed',
            attempts: 4,
            error: 'Always fails.',
          }),
        ],
        total: 3,
        page: 1,
        page_size: 20,
      },
    })

    renderWithProviders(<TasksPage />)

    expect(await screen.findByRole('link', { name: 'test.pdf (20 KB)' })).toHaveAttribute(
      'href',
      '/api/v1/files/tok',
    )
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getAllByRole('progressbar')[1]).toHaveAttribute('aria-valuenow', '40')
    expect(screen.getByText('Always fails.')).toBeInTheDocument()
    expect(screen.getByText('attempt 4')).toBeInTheDocument()
  })

  it('starts a test PDF', async () => {
    const fetchMock = mockApi({
      'GET /tasks': { items: [], total: 0, page: 1, page_size: 20 },
      'POST /tasks/test-pdf': { task_id: 'new' },
    })
    renderWithProviders(<TasksPage />)

    await screen.findByText(/No tasks yet/)
    await userEvent.click(screen.getByRole('button', { name: 'Generate test PDF' }))

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true),
    )
  })
})
