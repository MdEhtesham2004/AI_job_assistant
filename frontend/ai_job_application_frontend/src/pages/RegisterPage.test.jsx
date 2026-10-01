import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { makeAuth, renderWithProviders } from '@/test/utils'

import RegisterPage from './RegisterPage'

async function fill({ name = 'New Person', email = 'new@example.com', password, confirm }) {
  await userEvent.type(screen.getByLabelText('Full name'), name)
  await userEvent.type(screen.getByLabelText('Email'), email)
  await userEvent.type(screen.getByLabelText('Password'), password)
  await userEvent.type(screen.getByLabelText('Confirm password'), confirm)
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
}

describe('RegisterPage', () => {
  it('requires matching passwords of at least 10 characters', async () => {
    const auth = makeAuth({ status: 'anonymous', user: null })
    renderWithProviders(<RegisterPage />, { auth })

    await fill({ password: 'short', confirm: 'different' })

    expect(await screen.findByText('Use at least 10 characters')).toBeInTheDocument()
    expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
    expect(auth.register).not.toHaveBeenCalled()
  })

  it('sends name, email and password (not the confirmation)', async () => {
    const auth = makeAuth({
      status: 'anonymous',
      user: null,
      register: vi.fn().mockResolvedValue({}),
    })
    renderWithProviders(<RegisterPage />, { auth })

    await fill({ password: 'a-strong-password', confirm: 'a-strong-password' })

    expect(auth.register).toHaveBeenCalledWith({
      full_name: 'New Person',
      email: 'new@example.com',
      password: 'a-strong-password',
    })
  })

  it('shows "email already taken" next to the email field', async () => {
    const auth = makeAuth({
      status: 'anonymous',
      user: null,
      register: vi.fn().mockRejectedValue(
        new ApiError({
          status: 409,
          code: 'EMAIL_TAKEN',
          message: 'An account with this email already exists.',
        }),
      ),
    })
    renderWithProviders(<RegisterPage />, { auth })

    await fill({ password: 'a-strong-password', confirm: 'a-strong-password' })

    expect(
      await screen.findByText('An account with this email already exists.'),
    ).toBeInTheDocument()
  })
})
