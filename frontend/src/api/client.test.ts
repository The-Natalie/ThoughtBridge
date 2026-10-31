import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiUrl } from './client'

describe('apiUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('defaults to the local backend', () => {
    expect(apiUrl('/api/v1/health')).toBe('http://localhost:8000/api/v1/health')
  })

  it('honors VITE_API_URL', () => {
    vi.stubEnv('VITE_API_URL', 'https://demo.example.com')
    expect(apiUrl('/api/v1/health')).toBe('https://demo.example.com/api/v1/health')
  })

  it('joins base and path with exactly one slash', () => {
    vi.stubEnv('VITE_API_URL', 'https://demo.example.com/')
    expect(apiUrl('api/v1/health')).toBe('https://demo.example.com/api/v1/health')
    expect(apiUrl('/api/v1/health')).toBe('https://demo.example.com/api/v1/health')
  })
})
