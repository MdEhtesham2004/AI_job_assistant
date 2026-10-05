import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { InterviewPrepCard } from '@/features/hunt/components/InterviewPrepCard'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import InterviewPrepPage from './InterviewPrepPage'

afterEach(() => vi.unstubAllGlobals())

const JOB = {
  id: 'j1',
  title: 'React Native Developer',
  company: 'Acme',
  description_quality: 'full',
  active_tasks: [],
}
const USAGE = {
  interviews_month: { used: 1, limit: 10, left: 9 },
  interview_minutes: 6,
  interviews_available: true,
}
const PACK = {
  role_summary: 'Build and ship React Native features.',
  what_they_value: ['Shipping reliably'],
  your_fit: [
    { requirement: 'React Native', evidence: '4 years at Acme Apps' },
    { requirement: 'GraphQL', evidence: 'Not shown in your resume' },
  ],
  likely_questions: [
    {
      question: 'How did you cut the crash rate?',
      why: 'Stability matters.',
      how_to_answer: 'Use Acme.',
    },
  ],
  star_stories: [
    {
      title: 'Cutting crashes',
      situation: 'Crashes were high.',
      task: 'Fix them.',
      action: 'Added error handling.',
      result: 'Down 30%.',
      use_for: ['How did you cut the crash rate?'],
    },
  ],
  gaps: [{ gap: 'GraphQL', honest_answer: 'Learning it with a demo.' }],
  questions_to_ask: ['How do you release?'],
  checklist: ['Test your mic'],
  check: ['75'],
}

describe('Interview prep', () => {
  it('card prepares a pack when there is none', async () => {
    const fetchMock = mockApi({
      'GET /usage': USAGE,
      'GET /jobs/j1/prep': {
        job_id: 'j1',
        pack: null,
        updated_at: null,
        pdf_url: null,
        running_task_id: null,
      },
      'POST /jobs/j1/prep': () => jsonResponse({ task_id: 't1' }, { status: 202 }),
      'GET /tasks/t1': { id: 't1', type: 'interview_prep', status: 'running', progress: 10 },
    })
    renderWithProviders(<InterviewPrepCard job={JOB} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Prepare for interview' }))
    expect(await screen.findByRole('button', { name: 'Preparing…' })).toBeDisabled()
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => String(url).endsWith('/jobs/j1/prep') && init?.method === 'POST',
      ),
    ).toBe(true)
  })

  it('page shows the pack and "Practise with Maya" starts a focused mock', async () => {
    const fetchMock = mockApi({
      'GET /usage': USAGE,
      'GET /jobs/j1': JOB,
      'GET /jobs/j1/prep': {
        job_id: 'j1',
        pack: PACK,
        updated_at: '2026-10-05T10:00:00Z',
        pdf_url: '/api/v1/files/x',
        running_task_id: null,
      },
      'POST /jobs/j1/interviews': () =>
        jsonResponse({ interview_id: 'i9', task_id: 't9' }, { status: 202 }),
    })
    renderWithProviders(
      <Routes>
        <Route path="/jobs/:jobId/prep" element={<InterviewPrepPage />} />
        <Route path="/interviews/:id" element={<p>Room opened</p>} />
      </Routes>,
      { route: '/jobs/j1/prep' },
    )

    expect(await screen.findByText('Build and ship React Native features.')).toBeInTheDocument()
    expect(screen.getByText('Not shown in your resume')).toHaveClass('text-warning')
    expect(screen.getByText('1. How did you cut the crash rate?')).toBeInTheDocument()
    expect(screen.getByText('Cutting crashes')).toBeInTheDocument()
    expect(
      screen.getByText('Check these numbers — they are not in your resume: 75'),
    ).toBeInTheDocument()
    expect(screen.getByText('How do you release?')).toBeInTheDocument()

    await userEvent.click(await screen.findByRole('button', { name: 'Practise with Maya' }))
    expect(await screen.findByText('Room opened')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/jobs/j1/interviews'))
    expect(JSON.parse(post[1].body)).toMatchObject({ from_prep: true, round: 'mixed' })
  })
})
