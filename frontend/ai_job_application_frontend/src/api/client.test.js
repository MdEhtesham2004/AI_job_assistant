import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { tokenStore } from '@/auth/tokenStore'
import { errorResponse, jsonResponse } from '@/test/utils'

import { api, ApiError, refreshSession } from './client'

const session = (token) => ({ access_token: token, expires_in: 900, user: { id: 'u1' } })

beforeEach(() => {
  tokenStore.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('returns parsed JSON and prefixes the API base path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.get('/health')).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/health',
      expect.objectContaining({ method: 'GET', credentials: 'include' }),
    )
  })

  it('sends JSON bodies with a content type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 1 }, { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)

    await api.post('/things', { name: 'x' })

    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe('{"name":"x"}')
  })

  it('converts the standard error format into ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(errorResponse(404, 'NOT_FOUND', 'Resource not found.')),
    )

    const error = await api.get('/missing').catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 404,
      code: 'NOT_FOUND',
      message: 'Resource not found.',
      requestId: 'req-test',
    })
  })

  it('reports network failures as NETWORK_ERROR', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const error = await api.get('/health').catch((e) => e)

    expect(error).toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
  })

  it('returns null for 204 No Content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))

    await expect(api.delete('/things/1')).resolves.toBeNull()
  })
})

describe('authentication', () => {
  it('sends the access token as a Bearer header', async () => {
    tokenStore.set('token-1')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)

    await api.get('/users/me')

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer token-1')
  })

  it('refreshes once on 401 and retries with the new token', async () => {
    tokenStore.set('expired')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(errorResponse(401, 'TOKEN_EXPIRED'))
      .mockResolvedValueOnce(jsonResponse(session('fresh')))
      .mockResolvedValueOnce(jsonResponse({ email: 'me@example.com' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.get('/users/me')).resolves.toEqual({ email: 'me@example.com' })

    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/refresh')
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe('Bearer fresh')
    expect(tokenStore.get()).toBe('fresh')
  })

  it('ends the session when the refresh fails', async () => {
    tokenStore.set('expired')
    const ended = vi.fn()
    const unsubscribe = tokenStore.onSessionEnded(ended)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(errorResponse(401, 'TOKEN_EXPIRED'))
        .mockResolvedValueOnce(errorResponse(401, 'AUTH_REQUIRED')),
    )

    const error = await api.get('/users/me').catch((e) => e)

    expect(error.code).toBe('TOKEN_EXPIRED')
    expect(ended).toHaveBeenCalledOnce()
    expect(tokenStore.get()).toBeNull()
    unsubscribe()
  })

  it('does not try to refresh for auth endpoints (e.g. wrong password)', async () => {
    tokenStore.set('token')
    const fetchMock = vi.fn().mockResolvedValue(errorResponse(401, 'INVALID_CREDENTIALS'))
    vi.stubGlobal('fetch', fetchMock)

    await api.post('/auth/login', {}).catch(() => {})

    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('shares one refresh request between parallel callers', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(session('shared')))
    vi.stubGlobal('fetch', fetchMock)

    const [a, b] = await Promise.all([refreshSession(), refreshSession()])

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(a.access_token).toBe('shared')
    expect(b).toBe(a)
  })

  it('retries once when the server reports a refresh race', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(errorResponse(401, 'REFRESH_RACE'))
      .mockResolvedValueOnce(jsonResponse(session('after-race')))
    vi.stubGlobal('fetch', fetchMock)

    const result = await refreshSession()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.access_token).toBe('after-race')
  })
})
