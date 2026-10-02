import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeVersion } from '@/test/resumeFixtures'
import { mockApi, renderWithProviders } from '@/test/utils'

import ResumesPage from './ResumesPage'

const OVERVIEW = {
  resume_id: 'r',
  title: 'Master resume',
  active_version_id: 'v1',
  versions: [
    makeVersion({ id: 'v2', version_no: 2, kind: 'improved', is_active: false, ats_score: null }),
    makeVersion(),
  ],
}

afterEach(() => vi.unstubAllGlobals())

describe('ResumesPage', () => {
  it('lists versions with their status and lets you switch the active one', async () => {
    const fetchMock = mockApi({
      'GET /resumes': OVERVIEW,
      'POST /resumes/versions/v2/activate': () => new Response(null, { status: 204 }),
    })
    renderWithProviders(<ResumesPage />)

    expect(await screen.findByText('Version 2')).toBeInTheDocument()
    expect(screen.getByText('Improved')).toBeInTheDocument()
    expect(screen.getByText('ATS 72')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open version 1' })).toHaveAttribute(
      'href',
      '/resumes/v1',
    )

    await userEvent.click(screen.getByRole('button', { name: 'Set active' }))
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/v2/activate'))).toBe(true),
    )
  })

  it('rejects other file types before uploading', async () => {
    const fetchMock = mockApi({ 'GET /resumes': { ...OVERVIEW, versions: [] } })
    renderWithProviders(<ResumesPage />)
    await screen.findByText(/No resume yet/)

    const png = new File(['x'], 'photo.png', { type: 'image/png' })
    await userEvent.upload(screen.getByTestId('resume-file-input'), png, { applyAccept: false })

    expect(screen.getByRole('alert')).toHaveTextContent('Only PDF and DOCX')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })

  it('uploads a PDF as multipart form data', async () => {
    const fetchMock = mockApi({
      'GET /resumes': { ...OVERVIEW, versions: [] },
      'POST /resumes/upload': { version: makeVersion({ parse_status: 'pending' }), task_id: 't' },
    })
    renderWithProviders(<ResumesPage />)
    await screen.findByText(/No resume yet/)

    const pdf = new File(['%PDF-1.4'], 'asha.pdf', { type: 'application/pdf' })
    await userEvent.upload(screen.getByTestId('resume-file-input'), pdf)

    await vi.waitFor(() => {
      const upload = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/resumes/upload'))
      expect(upload?.[1].body).toBeInstanceOf(FormData)
      expect(upload[1].body.get('file').name).toBe('asha.pdf')
    })
  })
})
