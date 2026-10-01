import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import SettingsPage from './SettingsPage'

const SETTINGS = {
  threshold_use_master: 85,
  threshold_tailor: 65,
  score_weights: { skills: 40, experience: 25, technology: 20, education: 10, location: 5 },
  auto_analyze_new_jobs: true,
  daily_send_cap: 25,
  send_interval_seconds: 90,
  recipient_cooldown_days: 30,
  follow_up_days: 7,
  no_response_days: 21,
  linkedin_source_enabled: false,
  automation_enabled: false,
  automation_min_score: 70,
  monthly_ai_budget_usd: '5.00',
}

afterEach(() => vi.unstubAllGlobals())

async function setValue(label, value) {
  const input = screen.getByLabelText(label)
  await userEvent.clear(input)
  await userEvent.type(input, String(value))
}

describe('SettingsPage', () => {
  it('sends only the fields that changed', async () => {
    const fetchMock = mockApi({
      'GET /users/me/settings': SETTINGS,
      'PATCH /users/me/settings': (_url, init) =>
        jsonResponse({ ...SETTINGS, ...JSON.parse(init.body) }),
    })
    renderWithProviders(<SettingsPage />)

    await screen.findByLabelText('Daily send limit')
    await setValue('Daily send limit', 10)
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    const patch = await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
      if (!call) throw new Error('not yet')
      return call
    })
    expect(JSON.parse(patch[1].body)).toEqual({ daily_send_cap: 10 })
  })

  it('requires score weights that add up to 100', async () => {
    const fetchMock = mockApi({ 'GET /users/me/settings': SETTINGS })
    renderWithProviders(<SettingsPage />)

    await screen.findByLabelText('Skills')
    await setValue('Skills', 50)
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    expect(await screen.findByText('Weights must add up to 100')).toBeInTheDocument()
    expect(screen.getByText('(total 110 / 100)')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(false)
  })

  it('requires the tailor threshold to be below the master threshold', async () => {
    mockApi({ 'GET /users/me/settings': SETTINGS })
    renderWithProviders(<SettingsPage />)

    await screen.findByLabelText('Tailor resume at score ≥')
    await setValue('Tailor resume at score ≥', 90)
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    expect(
      await screen.findByText('Must be lower than the "use master resume" threshold'),
    ).toBeInTheDocument()
  })
})
