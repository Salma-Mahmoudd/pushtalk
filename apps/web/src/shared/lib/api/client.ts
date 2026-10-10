/** Field-level problem from the API error envelope. */
export interface FieldError {
  field: string | null
  message: string
}

interface ErrorEnvelope {
  error: { code: string; message: string; details: FieldError[] }
  request_id: string | null
}

/** Any non-2xx answer from the API, parsed from its standard error envelope. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: FieldError[]
  readonly requestId: string | null
  /** Seconds to wait before retrying (429 responses). */
  readonly retryAfter: number | null

  constructor(status: number, envelope: ErrorEnvelope | null, retryAfter: number | null) {
    super(envelope?.error.message ?? `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.code = envelope?.error.code ?? 'network_error'
    this.details = envelope?.error.details ?? []
    this.requestId = envelope?.request_id ?? null
    this.retryAfter = retryAfter
  }

  /** The message for one form field, if the API reported one. */
  fieldMessage(field: string): string | undefined {
    return this.details.find((detail) => detail.field === field)?.message
  }
}

interface SessionHooks {
  /** Renews the session cookies; resolves false when the session cannot be renewed. */
  refresh: () => Promise<boolean>
  /** Called when the session is gone for good (refresh failed). */
  onSessionLost: () => void
}

let hooks: SessionHooks | null = null
let refreshing: Promise<boolean> | null = null

// Credential endpoints report their own 401s; retrying them after a refresh makes no sense.
const NO_REFRESH = new Set(['/api/auth/login', '/api/auth/signup', '/api/auth/refresh', '/api/auth/logout'])

/** Connects the client to the auth feature, which owns refreshing and logging out. */
export function configureSession(sessionHooks: SessionHooks): void {
  hooks = sessionHooks
}

/** One refresh at a time: requests that fail together wait for the same refresh. */
function refreshOnce(): Promise<boolean> {
  if (!hooks) return Promise.resolve(false)
  refreshing ??= hooks.refresh().finally(() => {
    refreshing = null
  })
  return refreshing
}

async function toApiError(response: Response): Promise<ApiError> {
  let envelope: ErrorEnvelope | null = null
  try {
    envelope = (await response.json()) as ErrorEnvelope
  } catch {
    // Not JSON (e.g. a proxy error page): keep the generic message.
  }
  const retryAfter = Number(response.headers.get('Retry-After')) || null
  return new ApiError(response.status, envelope, retryAfter)
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
}

/**
 * Calls the API with the session cookies. On 401 it refreshes the session once and retries;
 * credential endpoints are never retried, so a failed login or refresh is reported as it is.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}, retried = false): Promise<T> {
  const response = await fetch(path, {
    method: options.method ?? 'GET',
    credentials: 'same-origin',
    headers: options.body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  })

  if (response.status === 401 && !retried && !NO_REFRESH.has(path)) {
    if (await refreshOnce()) return apiRequest<T>(path, options, true)
    hooks?.onSessionLost()
  }
  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
