import { describe, expect, it } from 'vitest'
import { isJwtExpired } from './authToken'

const tokenWithExpiry = (seconds) => `header.${btoa(JSON.stringify({ exp: seconds }))}.signature`

describe('isJwtExpired', () => {
  it('recognizes an expired JWT before a request is submitted', () => {
    expect(isJwtExpired(tokenWithExpiry(100), 100_001)).toBe(true)
    expect(isJwtExpired(tokenWithExpiry(101), 100_001)).toBe(false)
  })

  it('treats malformed or missing tokens as expired', () => {
    expect(isJwtExpired(null)).toBe(true)
    expect(isJwtExpired('not-a-jwt')).toBe(true)
  })
})
