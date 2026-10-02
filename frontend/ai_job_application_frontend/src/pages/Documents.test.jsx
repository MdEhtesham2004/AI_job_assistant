import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeJobDetail } from '@/test/jobFixtures'
import { PARSED } from '@/test/resumeFixtures'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import CoverLetterPage from './CoverLetterPage'
import JobDetailPage from './JobDetailPage'
import TailoredResumePage from './TailoredResumePage'

afterEach(() => vi.unstubAllGlobals())

const TAILORED_PARSED = {
  ...PARSED,
  summary: 'React Native developer with 4 years of experience shipping apps.',
  skills: ['TypeScript', 'React Native'],
  experience: [{ ...PARSED.experience[0], highlights: ['Built and shipped a payments app'] }],
}

function docs(overrides = {}) {
  return {
    job_id: 'j1',
    job_title: 'React Native Developer',
    company: 'ABC Technologies',
    source: { id: 'v1', version_no: 1, kind: 'master', file_name: 'cv.pdf' },
    tailored: null,
    tailored_from: null,
    cover_letter: null,
    active_tasks: [],
    ...overrides,
  }
}

const TAILORED = {
  id: 'v2',
  version_no: 2,
  kind: 'tailored',
  file_name: 'cv-abc.pdf',
  parsed: TAILORED_PARSED,
  download_url: '/api/v1/files/tok',
  created_at: '2026-10-02T10:00:00Z',
  updated_at: '2026-10-02T10:00:00Z',
  warnings: [],
  emphasized_skills: ['TypeScript'],
}

const LETTER = {
  id: 'c1',
  resume_version_id: 'v2',
  content_md: 'Dear Hiring Team,\n\nI am applying for the role.\n\nSincerely,\nAsha Verma',
  status: 'draft',
  download_url: '/api/v1/files/letter',
  word_count: 220,
  warnings: [],
  created_at: '2026-10-02T10:00:00Z',
  updated_at: '2026-10-02T10:00:00Z',
}

function renderAt(route, path, element) {
  return renderWithProviders(
    <Routes>
      <Route path={path} element={element} />
    </Routes>,
    { route },
  )
}

describe('Documents on the job page', () => {
  it('starts a tailored resume and a cover letter with a recipient', async () => {
    const fetchMock = mockApi({
      'GET /jobs/j1': makeJobDetail(),
      'GET /jobs/j1/documents': docs(),
      'POST /jobs/j1/tailored-resume': { task_id: 't1' },
      'POST /jobs/j1/cover-letter': { task_id: 't2' },
      'GET /tasks/t1': { id: 't1', type: 'resume_tailor', status: 'running', progress: 10 },
      'GET /tasks/t2': { id: 't2', type: 'cover_letter', status: 'running', progress: 10 },
    })
    renderAt('/jobs/j1', '/jobs/:jobId', <JobDetailPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Generate tailored resume' }))
    await userEvent.type(screen.getByLabelText('Recipient name'), 'Priya Sharma')
    await userEvent.click(screen.getByRole('button', { name: 'Generate cover letter' }))

    await vi.waitFor(() => {
      const letter = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/cover-letter'))
      expect(JSON.parse(letter[1].body)).toEqual({ contact_name: 'Priya Sharma' })
    })
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/tailored-resume'))).toBe(
      true,
    )
  })
})

describe('TailoredResumePage', () => {
  it('compares with the master and highlights new wording', async () => {
    mockApi({
      'GET /jobs/j1/documents': docs({
        tailored: TAILORED,
        tailored_from: {
          id: 'v1',
          version_no: 1,
          kind: 'master',
          file_name: 'cv.pdf',
          parsed: PARSED,
        },
      }),
    })
    renderAt('/jobs/j1/tailored', '/jobs/:jobId/tailored', <TailoredResumePage />)

    expect(await screen.findByText('Tailored for this job')).toBeInTheDocument()
    const added = screen.getAllByText((_, el) => el?.tagName === 'MARK').map((el) => el.textContent)
    expect(added.join(' ')).toContain('React Native')
    expect(added.join(' ')).toContain('and shipped')
    expect(screen.getByText('TypeScript')).toHaveClass('text-primary') // emphasized for the job
  })

  it('edits the tailored resume and shows checker warnings', async () => {
    let current = docs({ tailored: TAILORED })
    const fetchMock = mockApi({
      'GET /jobs/j1/documents': () => jsonResponse(current),
      'PUT /resumes/versions/v2/content': (_, init) => {
        const parsed = JSON.parse(init.body)
        current = docs({
          tailored: {
            ...TAILORED,
            parsed,
            updated_at: '2026-10-02T11:00:00Z',
            warnings: ["skill 'Kubernetes'"],
          },
        })
        return jsonResponse(current)
      },
    })
    renderAt('/jobs/j1/tailored', '/jobs/:jobId/tailored', <TailoredResumePage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const skills = screen.getByLabelText(/Skills/)
    await userEvent.clear(skills)
    await userEvent.type(skills, 'Kubernetes, Redux')
    await userEvent.click(screen.getByRole('button', { name: 'Save and update PDF' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("skill 'Kubernetes'")
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(put[1].body).skills).toEqual(['Kubernetes', 'Redux'])
  })
})

describe('CoverLetterPage', () => {
  it('edits the letter, marks it final and shows warnings', async () => {
    let current = docs({ cover_letter: LETTER })
    const fetchMock = mockApi({
      'GET /jobs/j1/documents': () => jsonResponse(current),
      'PATCH /cover-letters/c1': (_, init) => {
        const changes = JSON.parse(init.body)
        current = docs({
          cover_letter: {
            ...LETTER,
            ...(changes.content_md ? { content_md: changes.content_md } : {}),
            status: changes.status ?? LETTER.status,
            updated_at: '2026-10-02T11:00:00Z',
            warnings: ["placeholder '[Your Name]'"],
          },
        })
        return jsonResponse(current)
      },
    })
    renderAt('/jobs/j1/cover-letter', '/jobs/:jobId/cover-letter', <CoverLetterPage />)

    const editor = await screen.findByLabelText('Cover letter text')
    await userEvent.type(editor, ' [[Your Name]') // [[ = a literal [
    await userEvent.click(screen.getByRole('button', { name: 'Mark as final' }))

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText("placeholder '[Your Name]'")).toBeInTheDocument()
    expect(screen.getByText('Final')).toBeInTheDocument()
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    const body = JSON.parse(patch[1].body)
    expect(body.status).toBe('final')
    expect(body.content_md).toContain('[Your Name]')
  })
})
