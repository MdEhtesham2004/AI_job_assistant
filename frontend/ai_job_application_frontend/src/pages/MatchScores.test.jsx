import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { COUNTS, makeJob, makeJobDetail } from '@/test/jobFixtures'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import JobDetailPage from './JobDetailPage'
import JobsPage from './JobsPage'
import ScanPage from './ScanPage'

afterEach(() => vi.unstubAllGlobals())

const page = (items) => ({ items, total: items.length, page: 1, page_size: 20 })
const summary = (to_score) => ({ to_score, already_scored: 1, no_description: 0, over_limit: 0 })
const posted = (fetchMock, part) =>
  fetchMock.mock.calls.filter(
    ([url, init]) => init?.method === 'POST' && String(url).includes(part),
  )

const ANALYSIS = {
  id: 'a1',
  resume_version_id: 'v1',
  match_score: 79,
  component_scores: { skills: 80, experience: 80, technology: 60, education: 100, location: 100 },
  weights_used: { skills: 40, experience: 25, technology: 20, education: 10, location: 5 },
  matched_skills: ['React Native'],
  missing_skills: ['GraphQL'],
  recommendations: ['Mention the payments app.'],
  red_flags: [],
  seniority_fit: 'good',
  decision: 'tailor',
  model: 'm',
  prompt_version: 'job_match.v1',
  created_at: '2026-10-02T10:00:00Z',
  updated_at: '2026-10-02T10:00:00Z',
}

describe('Match scores on the Jobs page', () => {
  it('shows scores, scores one job on click and scores all saved jobs', async () => {
    const fetchMock = mockApi({
      'GET /jobs': page([
        makeJob({ id: 'j1', match_score: 79, decision: 'tailor', state: 'saved' }),
        makeJob({ id: 'j2', title: 'Flutter Dev', state: 'saved' }),
      ]),
      'GET /jobs/counts': COUNTS,
      'GET /jobs/analysis-summary': summary(1),
      'POST /jobs/j2/analyze': { task_id: 't1', cached: false },
      'GET /tasks/t1': { id: 't1', type: 'job_analyze', status: 'running', progress: 10 },
      'POST /jobs/analyze-batch': { ...summary(1), task_id: 't2' },
      'GET /tasks/t2': { id: 't2', type: 'job_analyze_batch', status: 'running', progress: 0 },
    })
    renderWithProviders(<JobsPage />, { route: '/jobs?state=saved' })

    expect(await screen.findByText('79% match · Tailor first')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Get match score for Flutter Dev' }))
    expect(await screen.findByText('Scoring…')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Score all saved jobs \(1\)/ }))
    await vi.waitFor(() => expect(posted(fetchMock, 'analyze-batch')).toHaveLength(1))
    expect(String(posted(fetchMock, 'analyze-batch')[0][0])).toContain('state=saved')
    expect(await screen.findByText('Scoring jobs…')).toBeInTheDocument()
  })

  it('offers to score unscored saved jobs before exporting', async () => {
    vi.stubGlobal(
      'URL',
      Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }),
    )
    const fetchMock = mockApi({
      'GET /jobs': page([makeJob({ state: 'saved' })]),
      'GET /jobs/counts': COUNTS,
      'GET /jobs/analysis-summary': summary(3),
      'GET /jobs/export.csv': () =>
        new Response('﻿Title\r\n', { headers: { 'Content-Type': 'text/csv' } }),
    })
    renderWithProviders(<JobsPage />, { route: '/jobs?state=saved' })
    await screen.findByText('React Native Developer')

    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    expect(await screen.findByText('Score your saved jobs first?')).toBeInTheDocument()
    expect(screen.getByText(/3 saved jobs have no match score/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Export without scores' }))
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('export.csv'))).toBe(true),
    )
    expect(posted(fetchMock, 'analyze-batch')).toHaveLength(0) // never scored without asking
  })

  it('asks for a resume when there is none', async () => {
    mockApi({
      'GET /jobs': page([makeJob()]),
      'GET /jobs/counts': COUNTS,
      'GET /jobs/analysis-summary': () =>
        jsonResponse(
          { error: { code: 'RESUME_REQUIRED', message: 'Upload a resume', details: {} } },
          { status: 409 },
        ),
    })
    renderWithProviders(<JobsPage />)

    expect(await screen.findByText(/Match scores need a parsed resume/)).toBeInTheDocument()
  })
})

describe('Analysis panel', () => {
  it('shows the score, components, skills and tips', async () => {
    mockApi({
      'GET /jobs/j1': makeJobDetail({ match_score: 79, decision: 'tailor', analysis: ANALYSIS }),
    })
    renderWithProviders(
      <Routes>
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
      </Routes>,
      { route: '/jobs/j1' },
    )

    expect(await screen.findByLabelText('ATS score 79 out of 100')).toBeInTheDocument()
    expect(screen.getByText('Tailor first')).toBeInTheDocument()
    expect(screen.getByText('GraphQL')).toBeInTheDocument()
    expect(screen.getByText('Mention the payments app.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Score again' })).toBeInTheDocument()
  })

  it('offers "Get match score" for an unscored job', async () => {
    const fetchMock = mockApi({
      'GET /jobs/j1': makeJobDetail(),
      'POST /jobs/j1/analyze': { task_id: null, cached: true },
    })
    renderWithProviders(
      <Routes>
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
      </Routes>,
      { route: '/jobs/j1' },
    )

    await userEvent.click(await screen.findByRole('button', { name: 'Get match score' }))
    await vi.waitFor(() => expect(posted(fetchMock, '/j1/analyze')).toHaveLength(1))
  })
})

describe('ScanPage', () => {
  it('scores a pasted job description', async () => {
    const description = 'Responsibilities: build React Native apps. '.repeat(8)
    const fetchMock = mockApi({
      'POST /jobs/scan-text': { job_id: 'j9', task_id: 't9' },
      'GET /tasks/t9': { id: 't9', type: 'job_analyze', status: 'succeeded', progress: 100 },
      'GET /jobs/j9': makeJobDetail({ id: 'j9', match_score: 79, analysis: ANALYSIS }),
    })
    renderWithProviders(<ScanPage />)

    await userEvent.type(screen.getByLabelText('Job title'), 'Mobile Engineer')
    await userEvent.click(screen.getByLabelText('Job description'))
    await userEvent.paste(description)
    await userEvent.click(screen.getByRole('button', { name: 'Score this job' }))

    expect(await screen.findByText('Mention the payments app.')).toBeInTheDocument()
    const body = JSON.parse(posted(fetchMock, 'scan-text')[0][1].body)
    expect(body).toEqual({
      title: 'Mobile Engineer',
      company: 'Unknown company',
      description: description.trim(),
    })
    expect(screen.getByRole('link', { name: 'Open the saved job' })).toHaveAttribute(
      'href',
      '/jobs/j9',
    )
  })
})
