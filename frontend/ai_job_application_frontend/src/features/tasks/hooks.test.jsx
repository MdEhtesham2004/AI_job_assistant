import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import { useTaskPolling } from './hooks'

afterEach(() => vi.unstubAllGlobals())

function Status({ id }) {
  const task = useTaskPolling(id).data
  return <p>status: {task?.status ?? 'loading'}</p>
}

describe('useTaskPolling', () => {
  // Regression (2026-10-12): when a task went running → succeeded, the "finished" answer
  // invalidated its own query mid-fetch, which cancelled it — every progress bar kept
  // spinning until the page was refreshed.
  it('shows the finished task without a page refresh', async () => {
    let calls = 0
    const fetchMock = mockApi({
      'GET /tasks/t1': () => {
        calls += 1
        return jsonResponse({
          id: 't1',
          type: 'job_analyze',
          status: calls === 1 ? 'running' : 'succeeded',
          progress: calls === 1 ? 40 : 100,
        })
      },
      'GET /tasks': { items: [], total: 0, page: 1, page_size: 20 },
      'GET /notifications/unread-count': { unread: 1 },
    })
    renderWithProviders(<Status id="t1" />)

    expect(await screen.findByText('status: running')).toBeInTheDocument()
    expect(await screen.findByText('status: succeeded', {}, { timeout: 6000 })).toBeInTheDocument()

    // Polling stops once finished (no request loop).
    const settled = calls
    await new Promise((resolve) => setTimeout(resolve, 2500))
    expect(calls).toBe(settled)
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/tasks/t1')).length).toBe(
      settled,
    )
  }, 15000)
})
