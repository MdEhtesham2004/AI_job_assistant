import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeJobDetail } from '@/test/jobFixtures'
import { makeVersion } from '@/test/resumeFixtures'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import ApplicationDetailPage from './ApplicationDetailPage'
import ApplicationsPage from './ApplicationsPage'
import JobDetailPage from './JobDetailPage'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

function makeApplication(overrides = {}) {
  return {
    id: 'a1',
    job: {
      id: 'j1',
      title: 'React Native Developer',
      company: 'ABC Technologies',
      location: 'Hyderabad',
      apply_url: 'https://abc.example/apply',
    },
    channel: 'portal',
    status: 'ready_to_apply',
    next_action: 'Apply by Friday',
    applied_at: null,
    last_status_at: '2026-10-02T10:00:00Z',
    created_at: '2026-10-02T10:00:00Z',
    match_score: 77,
    ...overrides,
  }
}

function detail(overrides = {}) {
  return {
    ...makeApplication(),
    resume: {
      id: 'v2',
      version_no: 2,
      kind: 'tailored',
      file_name: 't.pdf',
      download_url: '/api/v1/files/r',
    },
    cover_letter: null,
    history: [
      {
        id: 'h1',
        from_status: null,
        to_status: 'ready_to_apply',
        source: 'user',
        note: 'Application prepared',
        created_at: '2026-10-02T10:00:00Z',
      },
    ],
    allowed_next: ['applied', 'withdrawn'],
    ...overrides,
  }
}

const COUNTS = { counts: { ready_to_apply: 1, interview: 1 }, total: 2 }

describe('ApplicationsPage', () => {
  it('shows a board grouped by stage and a table', async () => {
    mockApi({
      'GET /applications': {
        items: [
          makeApplication(),
          makeApplication({
            id: 'a2',
            status: 'interview',
            job: { ...makeApplication().job, id: 'j2', title: 'Mobile Lead' },
          }),
        ],
        total: 2,
        page: 1,
        page_size: 200,
      },
      'GET /applications/counts': COUNTS,
    })
    renderWithProviders(<ApplicationsPage />)

    const todo = await screen.findByRole('region', { name: 'To do' })
    expect(within(todo).getByText('React Native Developer')).toBeInTheDocument()
    expect(
      within(screen.getByRole('region', { name: 'In process' })).getByText('Mobile Lead'),
    ).toBeInTheDocument()
    expect(within(todo).getByText('77% match')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Table' }))
    expect(screen.getByRole('columnheader', { name: 'Next action' })).toBeInTheDocument()
    expect(screen.getAllByText('Apply by Friday')).toHaveLength(2) // both rows
  })

  it('filters by stage and exports CSV', async () => {
    vi.stubGlobal(
      'URL',
      Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }),
    )
    const fetchMock = mockApi({
      'GET /applications': { items: [makeApplication()], total: 1, page: 1, page_size: 200 },
      'GET /applications/counts': COUNTS,
      'GET /applications/export.csv': () =>
        new Response('﻿Job\r\n', { headers: { 'Content-Type': 'text/csv' } }),
    })
    renderWithProviders(<ApplicationsPage />)
    await screen.findByText('React Native Developer')

    await userEvent.selectOptions(screen.getByLabelText('Stage'), 'talking')
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))

    await vi.waitFor(() => {
      const url = String(fetchMock.mock.calls.find(([u]) => String(u).includes('export.csv'))[0])
      expect(url).toContain('status=responded')
      expect(url).toContain('status=interview')
    })
  })
})

describe('ApplicationDetailPage', () => {
  it('offers only allowed moves, asks for a note and shows the timeline', async () => {
    let current = detail()
    const fetchMock = mockApi({
      'GET /applications/a1': () => jsonResponse(current),
      'POST /applications/a1/mark-applied': (_, init) => {
        const { note } = JSON.parse(init.body)
        current = detail({
          status: 'applied',
          applied_at: '2026-10-02T11:00:00Z',
          allowed_next: ['responded', 'interview', 'offer', 'rejected', 'no_response', 'withdrawn'],
          history: [
            ...current.history,
            {
              id: 'h2',
              from_status: 'ready_to_apply',
              to_status: 'applied',
              source: 'user',
              note,
              created_at: '2026-10-02T11:00:00Z',
            },
          ],
        })
        return jsonResponse(current)
      },
    })
    renderWithProviders(
      <Routes>
        <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />
      </Routes>,
      { route: '/applications/a1' },
    )

    expect(await screen.findByRole('link', { name: 'Open apply link' })).toHaveAttribute(
      'href',
      'https://abc.example/apply',
    )
    expect(screen.queryByRole('button', { name: 'Interview' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mark as applied' }))
    await userEvent.type(screen.getByLabelText('Note'), 'Applied on the careers page')
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(await screen.findByText('Applied on the careers page')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Interview' })).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/mark-applied'))
    expect(JSON.parse(call[1].body)).toEqual({ note: 'Applied on the careers page' })
  })
})

describe('Prepare application on the job page', () => {
  it('creates an application with the tailored resume and cover letter', async () => {
    let application = null
    const fetchMock = mockApi({
      'GET /jobs/j1': makeJobDetail(),
      'GET /jobs/j1/application': () => jsonResponse(application),
      'GET /jobs/j1/documents': {
        job_id: 'j1',
        job_title: 'React Native Developer',
        company: 'ABC Technologies',
        source: { id: 'v1', version_no: 1, kind: 'master', file_name: 'cv.pdf' },
        tailored: {
          id: 'v2',
          version_no: 2,
          kind: 'tailored',
          file_name: 't.pdf',
          parsed: {},
          download_url: '/x',
          created_at: '',
          updated_at: '',
          warnings: [],
          emphasized_skills: [],
        },
        tailored_from: null,
        cover_letter: {
          id: 'c1',
          status: 'final',
          content_md: '',
          download_url: '/y',
          word_count: 200,
          warnings: [],
          resume_version_id: 'v2',
          created_at: '',
          updated_at: '',
        },
        active_tasks: [],
      },
      'GET /resumes': {
        resume_id: 'r',
        title: 'm',
        active_version_id: 'v1',
        versions: [makeVersion()],
      },
      'POST /jobs/j1/applications': (_, init) => {
        application = detail({ ...JSON.parse(init.body) })
        return jsonResponse(application, { status: 201 })
      },
    })
    renderWithProviders(
      <Routes>
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
      </Routes>,
      { route: '/jobs/j1' },
    )

    expect(await screen.findByLabelText('Resume')).toHaveValue('v2') // tailored first
    await userEvent.type(screen.getByLabelText('Next action (optional)'), 'Apply by Friday')
    await userEvent.click(screen.getByRole('button', { name: 'Prepare application' }))

    expect(await screen.findByRole('link', { name: 'Open application' })).toHaveAttribute(
      'href',
      '/applications/a1',
    )
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post[1].body)).toEqual({
      channel: 'portal',
      resume_version_id: 'v2',
      cover_letter_id: 'c1',
      contact_id: null, // portal: no recipient
      next_action: 'Apply by Friday',
    })
  })
})
