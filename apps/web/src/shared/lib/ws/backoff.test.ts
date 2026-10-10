import { describe, expect, it } from 'vitest'

import { nextDelay } from './backoff'

describe('nextDelay', () => {
  const middle = () => 0.5 // no jitter

  it('doubles from 500 ms', () => {
    expect([0, 1, 2, 3].map((attempt) => nextDelay(attempt, { random: middle }))).toEqual([500, 1000, 2000, 4000])
  })

  it('caps at 30 s', () => {
    expect(nextDelay(10, { random: middle })).toBe(30_000)
    expect(nextDelay(50, { random: middle })).toBe(30_000)
  })

  it('stays within ±20 % jitter', () => {
    expect(nextDelay(3, { random: () => 0 })).toBe(3200)
    expect(nextDelay(3, { random: () => 1 })).toBe(4800)
    expect(nextDelay(10, { random: () => 1 })).toBe(36_000)
  })
})
