import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest, configureSession } from './client'

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

const unauthorized = () => json(401, { error: { code: 'unauthorized', message: 'Please log in.', details: [] }, request_id: 'r1' })

describe('apiRequest', () => {
  const fetchMock = vi.fn<typeof fetch>()
  const refresh = vi.fn<() => Promise<boolean>>()
  const onSessionLost = vi.fn<() => void>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    configureSession({ refresh, onSessionLost })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetAllMocks()
  })

  it('parses the error envelope into an ApiError', async () => {
    fetchMock.mockResolvedValue(
      json(
        422,
        { error: { code: 'validation_error', message: 'Some fields are invalid.', details: [{ field: 'username', message: 'Too short' }] }, request_id: 'abc' },
      ),
    )

    const error = await apiRequest('/api/things').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 422, code: 'validation_error', requestId: 'abc' })
    expect((error as ApiError).fieldMessage('username')).toBe('Too short')
  })

  it('reads Retry-After from rate-limited responses', async () => {
    fetchMock.mockResolvedValue(
      json(429, { error: { code: 'rate_limited', message: 'Slow down', details: [] }, request_id: null }, { 'Retry-After': '12' }),
    )

    await expect(apiRequest('/api/things')).rejects.toMatchObject({ code: 'rate_limited', retryAfter: 12 })
  })

  it('refreshes once for concurrent 401s and retries each request once', async () => {
    let refreshed = false
    fetchMock.mockImplementation(async () => (refreshed ? json(200, { ok: true }) : unauthorized()))
    refresh.mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10))
      refreshed = true
      return true
    })

    const results = await Promise.all([apiRequest('/api/a'), apiRequest('/api/b'), apiRequest('/api/c')])

    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }])
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(6)
  })

  it('reports the session as lost when the refresh fails', async () => {
    fetchMock.mockResolvedValue(unauthorized())
    refresh.mockResolvedValue(false)

    await expect(apiRequest('/api/a')).rejects.toMatchObject({ status: 401 })
    expect(onSessionLost).toHaveBeenCalledTimes(1)
  })

  it('does not retry a request that fails again after a refresh', async () => {
    fetchMock.mockResolvedValue(unauthorized())
    refresh.mockResolvedValue(true)

    await expect(apiRequest('/api/a')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('never refreshes for credential endpoints', async () => {
    fetchMock.mockResolvedValue(
      json(401, { error: { code: 'invalid_credentials', message: 'Wrong username or password.', details: [] }, request_id: null }),
    )

    await expect(apiRequest('/api/auth/login', { method: 'POST', body: {} })).rejects.toMatchObject({
      code: 'invalid_credentials',
    })
    expect(refresh).not.toHaveBeenCalled()
  })

  it('sends JSON bodies with same-origin credentials', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await expect(apiRequest('/api/things', { method: 'POST', body: { a: 1 } })).resolves.toBeUndefined()

    const [, init] = fetchMock.mock.calls[0]
    expect(init).toMatchObject({ method: 'POST', credentials: 'same-origin', body: '{"a":1}' })
  })

  it('turns an unreadable error body into a generic ApiError', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 }))

    await expect(apiRequest('/api/things')).rejects.toMatchObject({ status: 502, code: 'network_error' })
  })
})
