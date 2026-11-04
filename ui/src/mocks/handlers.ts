import { http, HttpResponse } from 'msw'
import { config } from '../lib/config'
import type { Batch, Finding } from '../lib/api/schemas'
import { db, RUNNING_BATCH } from './data'

const base = config.apiBase
const err = (status: number, code: string, message = code) =>
  HttpResponse.json({ error: { code, message, trace_id: 'mock-trace' } }, { status })

const SEV_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }

function rank(a: Finding, b: Finding): number {
  return (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9) || b.confidence - a.confidence || a.finding_id.localeCompare(b.finding_id)
}

function decide(f: Finding, body: { action: string; reason_code?: string; edited_value?: Record<string, unknown> }) {
  if (f.status !== 'needs_review') return { status: 409 as const }
  const status = { approve: 'approved', reject: 'rejected', investigate: 'investigating' }[body.action] ?? 'needs_review'
  const edited = body.action === 'approve' && body.edited_value
  Object.assign(f, { status, ...(edited ? { suggested_value: body.edited_value } : {}) })
  // PROVISIONAL (OQ-10, OQ-233): AI findings need a second approver in the mock.
  return { status: 201 as const, decision_id: `d_${f.finding_id.slice(-4)}`, finding_status: status, requires_second_approval: f.source === 'ai_suggestion' && body.action === 'approve' }
}

export const handlers = [
  http.get(`${base}/batches`, () => HttpResponse.json({ items: db.batches, next_cursor: null })),

  http.post(`${base}/batches`, async ({ request }) => {
    const key = request.headers.get('idempotency-key')
    if (!key) return err(422, 'validation_error', 'Idempotency-Key header is required')
    const form = await request.formData()
    const file = form.get('file')
    if (!(file instanceof File)) return err(422, 'validation_error', 'file is required')
    if (!/\.(json|csv)$/i.test(file.name)) return err(422, 'validation_error', 'Only .json and .csv files are accepted', )
    const known = db.idempotency.get(key) as { batch_id: string; status: string } | undefined
    if (known) return HttpResponse.json(known, { status: 202 })
    const created = { batch_id: `b_new_${db.batches.length}`, status: 'queued' }
    db.batches.unshift({ batch_id: created.batch_id, status: 'queued', records: null, findings_by_type: {}, ai_status: 'not_started', filename: file.name } as Batch)
    db.idempotency.set(key, created)
    return HttpResponse.json(created, { status: 202 })
  }),

  http.get(`${base}/batches/:id`, ({ params }) => {
    const b = db.batches.find((x) => x.batch_id === params.id)
    if (!b) return err(404, 'not_found')
    if (b.batch_id === RUNNING_BATCH) {
      db.runningPolls += 1 // the running batch finishes after 3 polls
      if (db.runningPolls > 3) Object.assign(b, { status: 'done', ai_status: 'complete', findings_by_type: { weak_description: 1 } })
    }
    return HttpResponse.json(b)
  }),

  http.get(`${base}/batches/:id/findings`, ({ params, request }) => {
    const u = new URL(request.url)
    if (!db.batches.some((x) => x.batch_id === params.id)) return err(404, 'not_found')
    const q = (k: string) => u.searchParams.get(k) || undefined
    const limit = Math.min(Number(q('limit') ?? 50), 200)
    const start = q('cursor') ? Number(atob(q('cursor') as string)) : 0
    const rows = db.findings
      .filter((f) => f.batch_id === params.id)
      .filter((f) => (!q('issue_type') || f.issue_type === q('issue_type')) && (!q('severity') || f.severity === q('severity')) && (!q('source') || f.source === q('source')) && (!q('status') || f.status === q('status')))
      .sort(rank)
    const items = rows.slice(start, start + limit)
    const next = start + limit < rows.length ? btoa(String(start + limit)) : null
    return HttpResponse.json({ items, next_cursor: next })
  }),

  http.post(`${base}/findings/decisions\\:bulk`, async ({ request }) => {
    const { decisions } = (await request.json()) as { decisions: { finding_id: string; action: string; reason_code?: string }[] }
    if (decisions.length > 500) return err(422, 'validation_error', 'At most 500 decisions')
    const results = decisions.map((d) => {
      const f = db.findings.find((x) => x.finding_id === d.finding_id)
      if (!f) return { finding_id: d.finding_id, status: 404, error: { code: 'not_found' } }
      const r = decide(f, d)
      return r.status === 409
        ? { finding_id: d.finding_id, status: 409, error: { code: 'state_conflict' } }
        : { finding_id: d.finding_id, status: 201, decision_id: r.decision_id, finding_status: r.finding_status }
    })
    return HttpResponse.json({ results }, { status: 207 })
  }),

  http.post(`${base}/findings/:id/decisions`, async ({ params, request }) => {
    const f = db.findings.find((x) => x.finding_id === params.id)
    if (!f) return err(404, 'not_found')
    const body = (await request.json()) as { action: string; reason_code?: string; edited_value?: Record<string, unknown> }
    if (body.action === 'reject' && !body.reason_code) return err(422, 'validation_error', 'reason_code is required to reject')
    const r = decide(f, body)
    return r.status === 409 ? err(409, 'state_conflict') : HttpResponse.json(r, { status: 201 })
  }),

  http.post(`${base}/batches/:id/exports`, ({ params }) => {
    const id = `x_${db.exports.size + 1}`
    const count = db.findings.filter((f) => f.batch_id === params.id && f.status === 'approved').length
    db.exports.set(id, { status: 'queued', finding_count: count, polls: 0 })
    return HttpResponse.json({ export_id: id, status: 'queued' }, { status: 202 })
  }),

  http.get(`${base}/exports/:id`, ({ params }) => {
    const e = db.exports.get(params.id as string)
    if (!e) return err(404, 'not_found')
    e.polls += 1
    if (e.status === 'queued' && e.polls >= 2) e.status = 'ready'
    return HttpResponse.json({
      status: e.status,
      finding_count: e.finding_count,
      ...(e.status === 'ready' ? { signed_url: `https://files.example.test/${params.id}.csv?sig=mock`, expires_at: '2026-11-04T12:00:00Z' } : {}),
    })
  }),

  http.get(`${base}/reference-data/:type`, ({ params }) => {
    const values = params.type === 'taxonomy' ? ['Mechanical', 'Electrical', 'Hydraulic', 'Fasteners'] : ['EA', 'PC', 'BOX', 'KG', 'M', 'L', 'SET', 'PR']
    return HttpResponse.json({ type: params.type, version: 1, values })
  }),
]
