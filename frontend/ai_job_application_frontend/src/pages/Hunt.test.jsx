import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DigestCard } from '@/features/hunt/components/DigestCard'
import { ScreeningAnswersCard } from '@/features/hunt/components/ScreeningAnswersCard'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import SkillsPage from './SkillsPage'

afterEach(() => vi.unstubAllGlobals())

const accepted = (body) => () => jsonResponse(body, { status: 202 })

describe('Daily digest card', () => {
  it("shows today's best matches and checks for new ones on request", async () => {
    const fetchMock = mockApi({
      'GET /digest': {
        running_task_id: null,
        digest: {
          digest_date: '2026-10-05',
          created_at: '2026-10-05T02:30:00Z',
          is_today: true,
          new_jobs: 7,
          scored: 5,
          emailed: false,
          email_error: 'Gmail is not connected.',
          jobs: [
            {
              job_id: 'j1',
              title: 'React Native Developer',
              company: 'Acme',
              location: 'Pune',
              score: 84,
              decision: 'use_master',
            },
            {
              job_id: 'j2',
              title: 'Mobile Engineer',
              company: 'Zeta',
              location: null,
              score: 76,
              decision: 'tailor',
            },
          ],
        },
      },
      'POST /digest/run': accepted({ task_id: 't1' }),
      'GET /tasks/t1': { id: 't1', type: 'daily_digest', status: 'running', progress: 20 },
    })
    renderWithProviders(<DigestCard />)

    const list = await screen.findByRole('list', { name: 'Best new matches' })
    expect(within(list).getByRole('link', { name: 'React Native Developer' })).toHaveAttribute(
      'href',
      '/jobs/j1',
    )
    expect(within(list).getByText('84')).toBeInTheDocument()
    expect(screen.getByText('Today: 7 new jobs, 5 scored for you.')).toBeInTheDocument()
    expect(screen.getByText('Gmail is not connected.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Check for new matches now' }))
    expect(await screen.findByRole('button', { name: 'Checking…' })).toBeDisabled()
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => String(url).endsWith('/digest/run') && init.method === 'POST',
      ),
    ).toBe(true)
  })
})

describe('Screening answers', () => {
  const JOB = {
    id: 'j1',
    title: 'React Native Developer',
    company: 'Acme',
    description_quality: 'full',
  }
  const ANSWERS = {
    job_id: 'j1',
    updated_at: '2026-10-05T10:00:00Z',
    running_task_id: null,
    answers: [
      {
        key: 'about',
        question: 'Tell us about yourself.',
        answer: 'I build React Native apps.',
        edited: false,
        custom: false,
        check: [],
      },
      {
        key: 'why_hire',
        question: 'Why should we hire you?',
        answer: 'I led 12 engineers.',
        edited: false,
        custom: false,
        check: ['12'],
      },
      {
        key: 'salary',
        question: 'What are your salary expectations?',
        answer: 'My expectation is [fill in], and I am open to discussing it.',
        edited: false,
        custom: false,
        check: [],
      },
    ],
  }

  it('marks [fill in], warns about unknown numbers, copies, edits and sends own questions', async () => {
    const writeText = vi.fn(async () => {})
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    const fetchMock = mockApi({
      'GET /jobs/j1/answers': ANSWERS,
      'PATCH /jobs/j1/answers/about': (_url, init) =>
        jsonResponse({
          ...ANSWERS,
          answers: [
            { ...ANSWERS.answers[0], answer: JSON.parse(init.body).answer, edited: true },
            ...ANSWERS.answers.slice(1),
          ],
        }),
      'POST /jobs/j1/answers': accepted({ task_id: 't2' }),
      'GET /tasks/t2': { id: 't2', type: 'screening_answers', status: 'running', progress: 10 },
    })
    renderWithProviders(<ScreeningAnswersCard job={JOB} />)

    expect(await screen.findByText('[fill in]')).toBeInTheDocument()
    expect(
      screen.getByText('Check these numbers — they are not in your resume: 12'),
    ).toBeInTheDocument()
    // A [fill in] answer cannot be copied until it is completed.
    expect(
      screen.getByRole('button', { name: 'Copy answer: What are your salary expectations?' }),
    ).toBeDisabled()
    await userEvent.click(
      screen.getByRole('button', { name: 'Copy answer: Tell us about yourself.' }),
    )
    expect(writeText).toHaveBeenCalledWith('I build React Native apps.')

    await userEvent.click(
      screen.getByRole('button', { name: 'Edit answer: Tell us about yourself.' }),
    )
    const box = screen.getByRole('textbox', { name: 'Edit answer: Tell us about yourself.' })
    await userEvent.clear(box)
    await userEvent.type(box, 'My own intro.')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('My own intro.')).toBeInTheDocument()

    await userEvent.type(
      screen.getByLabelText('Add your own question'),
      'Are you willing to relocate?{Enter}',
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Rewrite answers (keeps your edits)' }),
    )
    await vi.waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith('/jobs/j1/answers') && init?.method === 'POST',
      )
      expect(JSON.parse(post[1].body)).toEqual({
        custom_questions: ['Are you willing to relocate?'],
      })
    })
  })
})

describe('Skill gaps page', () => {
  it('shows the gaps across scored jobs and the learning plan', async () => {
    const fetchMock = mockApi({
      'GET /skills': {
        jobs_analyzed: 4,
        gaps: [
          { skill: 'GraphQL', jobs: 3, examples: ['RN Dev — Acme', 'Mobile — Zeta'] },
          { skill: 'Jest', jobs: 1, examples: ['RN Dev — Acme'] },
        ],
        strengths: [{ skill: 'React Native', jobs: 4, examples: [] }],
        running_task_id: null,
        plan: {
          id: 'p1',
          created_at: '2026-10-05T10:00:00Z',
          gaps: [{ skill: 'GraphQL', jobs: 3 }],
          plan: {
            summary: 'GraphQL is asked for most.',
            days: [{ day: 1, focus: 'GraphQL', task: 'Read the official intro.' }],
            mini_project: 'A small GraphQL API.',
            resources: ['The official GraphQL docs'],
            interview_tip: 'Say what you are learning.',
          },
        },
      },
      'POST /skills/plan': accepted({ task_id: 't3' }),
      'GET /tasks/t3': { id: 't3', type: 'skill_plan', status: 'running', progress: 10 },
    })
    renderWithProviders(<SkillsPage />)

    const gaps = await screen.findByRole('list', { name: 'Skill gaps' })
    expect(within(gaps).getByText('GraphQL')).toBeInTheDocument()
    expect(within(gaps).getByText('3 of 4 jobs')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Strengths' })).toHaveTextContent('React Native')
    expect(screen.getByText('Read the official intro.')).toBeInTheDocument()
    expect(screen.getByText('A small GraphQL API.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Make a new plan' }))
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => String(url).endsWith('/skills/plan') && init?.method === 'POST',
        ),
      ).toBe(true),
    )
  })
})
