import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { makeAuth, renderWithProviders } from '@/test/utils'

import LoginPage from './LoginPage'

describe('LoginPage', () => {
  it('validates the form before calling the API', async () => {
    const auth = makeAuth({ status: 'anonymous', user: null })
    renderWithProviders(<LoginPage />, { auth })

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Email is required')).toBeInTheDocument()
    expect(screen.getByText('Password is required')).toBeInTheDocument()
    expect(auth.login).not.toHaveBeenCalled()
  })

  it('submits email and password', async () => {
    const auth = makeAuth({ status: 'anonymous', user: null, login: vi.fn().mockResolvedValue({}) })
    renderWithProviders(<LoginPage />, { auth })

    await userEvent.type(screen.getByLabelText('Email'), 'me@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'secret-password')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(auth.login).toHaveBeenCalledWith({
      email: 'me@example.com',
      password: 'secret-password',
    })
  })

  it('shows the server message for wrong credentials', async () => {
    const auth = makeAuth({
      status: 'anonymous',
      user: null,
      login: vi.fn().mockRejectedValue(
        new ApiError({
          status: 401,
          code: 'INVALID_CREDENTIALS',
          message: 'Incorrect email or password.',
        }),
      ),
    })
    renderWithProviders(<LoginPage />, { auth })

    await userEvent.type(screen.getByLabelText('Email'), 'me@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
  })
})
