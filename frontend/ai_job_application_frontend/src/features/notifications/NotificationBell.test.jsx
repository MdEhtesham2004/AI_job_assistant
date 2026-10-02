import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockApi, renderWithProviders } from '@/test/utils'

import { NotificationBell } from './NotificationBell'

const NOTE = {
  id: 'n-1',
  type: 'task_succeeded',
  title: 'Test PDF finished',
  body: null,
  link: '/tasks',
  severity: 'success',
  read_at: null,
  created_at: '2026-10-02T10:00:00Z',
}

afterEach(() => vi.unstubAllGlobals())

describe('NotificationBell', () => {
  it('lists notifications and marks one as read when opened', async () => {
    const fetchMock = mockApi({
      'GET /notifications/unread-count': { unread: 1 },
      'GET /notifications': { items: [NOTE], total: 1, page: 1, page_size: 10 },
      'POST /notifications/n-1/read': { ...NOTE, read_at: '2026-10-02T10:01:00Z' },
    })
    renderWithProviders(<NotificationBell />)

    await userEvent.click(await screen.findByLabelText('Notifications, 1 unread'))
    await userEvent.click(await screen.findByText('Test PDF finished'))

    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => url.endsWith('/n-1/read') && init.method === 'POST',
        ),
      ).toBe(true),
    )
  })

  it('marks everything as read', async () => {
    const fetchMock = mockApi({
      'GET /notifications/unread-count': { unread: 1 },
      'GET /notifications': { items: [NOTE], total: 1, page: 1, page_size: 10 },
      'POST /notifications/read-all': () => new Response(null, { status: 204 }),
    })
    renderWithProviders(<NotificationBell />)

    await userEvent.click(await screen.findByLabelText('Notifications, 1 unread'))
    await userEvent.click(await screen.findByRole('button', { name: 'Mark all read' }))

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/read-all'))).toBe(true),
    )
  })

  it('says when there is nothing new', async () => {
    mockApi({
      'GET /notifications/unread-count': { unread: 0 },
      'GET /notifications': { items: [], total: 0, page: 1, page_size: 10 },
    })
    renderWithProviders(<NotificationBell />)

    await userEvent.click(await screen.findByLabelText('Notifications'))

    expect(await screen.findByText("You're all caught up.")).toBeInTheDocument()
  })
})
