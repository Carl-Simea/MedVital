import { describe, expect, it, vi } from 'vitest'
import { TransportError } from '../domain/sync'
import { HttpTransport } from './client'

describe('HttpTransport', () => {
  it('maps a fetch failure to a network TransportError', async () => {
    const t = new HttpTransport('/api/v1', () => Promise.reject(new TypeError('Failed to fetch')))
    await expect(t.pull(0, 10)).rejects.toMatchObject({ kind: 'network' })
  })

  it('maps non-2xx to an http TransportError with status', async () => {
    const t = new HttpTransport('/api/v1', async () => new Response('{}', { status: 422, statusText: 'Unprocessable' }))
    const err = await t.push({ client_id: 'c', mutations: [] }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(TransportError)
    expect(err).toMatchObject({ kind: 'http', status: 422 })
  })

  it('calls the documented endpoints', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ changes: [], next_cursor: 0, has_more: false })))
    const t = new HttpTransport('/api/v1', fetchImpl)
    await t.pull(3, 50)
    expect(fetchImpl).toHaveBeenCalledWith('/api/v1/sync/pull?cursor=3&limit=50', undefined)
  })
})
