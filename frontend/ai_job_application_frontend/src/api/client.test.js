import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '@/test/utils'

import { api, ApiError } from './client'

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
      expect.objectContaining({ method: 'GET' }),
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
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: 'NOT_FOUND',
              message: 'Resource not found.',
              details: {},
              request_id: 'req-1',
            },
          },
          { status: 404 },
        ),
      ),
    )

    const error = await api.get('/missing').catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 404,
      code: 'NOT_FOUND',
      message: 'Resource not found.',
      requestId: 'req-1',
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
