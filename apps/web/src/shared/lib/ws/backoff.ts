export interface BackoffOptions {
  baseMs?: number
  capMs?: number
  /** Spread as a fraction of the delay, so clients do not all reconnect at the same moment. */
  jitter?: number
  random?: () => number
}

/** Reconnect delay before attempt `attempt` (0-based): min(cap, base · 2^attempt) ± jitter. */
export function nextDelay(
  attempt: number,
  { baseMs = 500, capMs = 30_000, jitter = 0.2, random = Math.random }: BackoffOptions = {},
): number {
  const exact = Math.min(capMs, baseMs * 2 ** attempt)
  return Math.round(exact * (1 + (random() * 2 - 1) * jitter))
}
