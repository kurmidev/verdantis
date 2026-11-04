import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../../mocks/server'
import { BRIEF_BATCH } from '../../mocks/data'
import { api, newTraceparent } from './client'
import { ApiError, describeError } from './errors'

const base = 'http://localhost/api/v1'

describe('api client', () => {
  it('parses findings with query filters and a cursor', async () => {
    const page = await api.listFindings(BRIEF_BATCH, { severity: 'low' })
    expect(page.items).toHaveLength(1)
    expect(page.items[0]?.issue_type).toBe('category_mismatch_candidate')
  })

  it('sends traceparent, no auth headers and an Idempotency-Key on POST', async () => {
    let seen: Headers | undefined
    server.use(http.post(`${base}/batches/b_1/exports`, ({ request }) => {
      seen = request.headers
      return HttpResponse.json({ export_id: 'x_1' }, { status: 202 })
    }))
    await api.createExport('b_1', 'key-1')
    expect(seen?.get('idempotency-key')).toBe('key-1')
    expect(seen?.get('x-dev-user')).toBeNull()
    expect(seen?.get('traceparent')).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/)
  })

  it('maps the error envelope to ApiError with trace id', async () => {
    server.use(http.get(`${base}/batches/x`, () =>
      HttpResponse.json({ error: { code: 'not_found', message: 'nope', trace_id: 't-9' } }, { status: 404 })))
    const e = await api.getBatch('x').catch((x: unknown) => x)
    expect(e).toBeInstanceOf(ApiError)
    expect(e).toMatchObject({ status: 404, code: 'not_found', traceId: 't-9' })
  })

  it('rejects a response that does not match the schema', async () => {
    server.use(http.get(`${base}/batches/bad`, () => HttpResponse.json({ nope: true })))
    await expect(api.getBatch('bad')).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('returns per-item results for a 207 bulk response', async () => {
    const res = await api.decideBulk([
      { finding_id: 'f_01J9ZK3M8Q', action: 'investigate' },
      { finding_id: 'f_01J9ZK3M8Q', action: 'investigate' },
    ], 'k')
    expect(res.results.map((r) => r.status)).toEqual([201, 409])
    expect(res.results[1]?.error?.code).toBe('state_conflict')
  })

  it('reports Retry-After on 429', async () => {
    server.use(http.get(`${base}/batches/rl`, () =>
      HttpResponse.json({ error: { code: 'rate_limited' } }, { status: 429, headers: { 'Retry-After': '7' } })))
    const e = (await api.getBatch('rl').catch((x: unknown) => x)) as ApiError
    expect(e.retryAfter).toBe(7)
    expect(describeError(e)).toContain('7 seconds')
  })

  it('turns a network failure into status 0', async () => {
    server.use(http.get(`${base}/batches/net`, () => HttpResponse.error()))
    await expect(api.getBatch('net')).rejects.toMatchObject({ status: 0 })
  })

  it('keeps unknown enum values as raw strings', async () => {
    server.use(http.get(`${base}/batches/e/findings`, () => HttpResponse.json({ items: [{
      finding_id: 'f', batch_id: 'e', record_key: 'k', issue_type: 'brand_new_issue', severity: 'critical',
      confidence: 0.5, explanation: 'x', evidence: { a: 1 }, suggested_action: 'y', source: 'quantum',
      rule_id: 'r', rule_version: '1', status: 'needs_review', extra_field: 1,
    }], next_cursor: null })))
    const p = await api.listFindings('e', {})
    expect(p.items[0]?.issue_type).toBe('brand_new_issue')
  })

  it('generates W3C traceparent values', () => {
    expect(newTraceparent()).not.toBe(newTraceparent())
  })
})
