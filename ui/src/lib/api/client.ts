import type { z } from 'zod'
import { config } from '../config'
import { ApiError } from './errors'
import * as S from './schemas'

const hex = (n: number): string =>
  Array.from(crypto.getRandomValues(new Uint8Array(n)), (b) => b.toString(16).padStart(2, '0')).join('')
export const newTraceparent = (): string => `00-${hex(16)}-${hex(8)}-01`
export const newKey = (): string => crypto.randomUUID()

const TIMEOUT_MS = 30_000 // LLD 13 3.18

interface Opts<T> {
  schema: z.ZodType<T>
  method?: 'GET' | 'POST'
  body?: FormData | object
  idempotencyKey?: string
  signal?: AbortSignal | undefined
  query?: Record<string, string | number | undefined>
}

async function toApiError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`
  let message = res.statusText
  let details: unknown
  let traceId = res.headers.get('x-trace-id') ?? undefined
  try {
    const j = (await res.json()) as { error?: { code?: string; message?: string; details?: unknown; trace_id?: string } }
    if (j.error) {
      code = j.error.code ?? code
      message = j.error.message ?? message
      details = j.error.details
      traceId = j.error.trace_id ?? traceId
    }
  } catch {
    /* non-JSON error body */
  }
  const ra = Number(res.headers.get('retry-after'))
  return new ApiError(res.status, code, message, {
    ...(traceId ? { traceId } : {}),
    details,
    ...(ra > 0 ? { retryAfter: ra } : {}),
  })
}

async function request<T>(path: string, o: Opts<T>): Promise<T> {
  const url = new URL(config.apiBase + path, window.location.origin)
  for (const [k, v] of Object.entries(o.query ?? {})) if (v !== undefined && v !== '') url.searchParams.set(k, String(v))

  const headers: Record<string, string> = {
    Accept: 'application/json',
    traceparent: newTraceparent(),
  }
  if (o.idempotencyKey) headers['Idempotency-Key'] = o.idempotencyKey
  let body: BodyInit | undefined
  if (o.body instanceof FormData) body = o.body
  else if (o.body) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(o.body)
  }

  const timeout = new AbortController()
  const timer = setTimeout(() => timeout.abort(), TIMEOUT_MS)
  o.signal?.addEventListener('abort', () => timeout.abort(), { once: true })
  let res: Response
  try {
    const init: RequestInit = { method: o.method ?? 'GET', headers, signal: timeout.signal }
    if (body !== undefined) init.body = body
    res = await fetch(url, init)
  } catch (e) {
    if (o.signal?.aborted) throw e
    throw new ApiError(0, 'network_error', 'Network error')
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) throw await toApiError(res)
  const parsed = o.schema.safeParse(await res.json())
  if (!parsed.success) {
    throw new ApiError(res.status, 'invalid_response', 'Unexpected response from the service', {
      details: parsed.error.issues,
      ...(res.headers.get('x-trace-id') ? { traceId: res.headers.get('x-trace-id') as string } : {}),
    })
  }
  return parsed.data
}

export interface FindingsParams {
  issue_type?: string | undefined
  severity?: string | undefined
  source?: string | undefined
  status?: string | undefined
  tab?: string | undefined
  cursor?: string | undefined
  limit?: number
}

export const api = {
  uploadBatch(file: File, key: string) {
    const form = new FormData()
    form.append('file', file)
    return request('/batches', { method: 'POST', body: form, idempotencyKey: key, schema: S.BatchCreated })
  },
  listBatches(cursor?: string, signal?: AbortSignal) {
    return request('/batches', { schema: S.BatchList, query: { limit: 50, cursor }, signal })
  },
  getBatch(id: string, signal?: AbortSignal) {
    return request(`/batches/${encodeURIComponent(id)}`, { schema: S.Batch, signal })
  },
  listFindings(batchId: string, p: FindingsParams, signal?: AbortSignal) {
    return request(`/batches/${encodeURIComponent(batchId)}/findings`, {
      schema: S.FindingsPage,
      query: { ...p },
      signal,
    })
  },
  decide(findingId: string, body: S.DecisionBody, key: string) {
    return request(`/findings/${encodeURIComponent(findingId)}/decisions`, {
      method: 'POST',
      body,
      idempotencyKey: key,
      schema: S.DecisionResult,
    })
  },
  /** 207 Multi-Status: per-item results; a 2xx overall response is never an overall success. */
  decideBulk(decisions: S.BulkItem[], key: string) {
    return request('/findings/decisions:bulk', {
      method: 'POST',
      body: { decisions },
      idempotencyKey: key,
      schema: S.BulkResult,
    })
  },
  createExport(batchId: string, key: string) {
    return request(`/batches/${encodeURIComponent(batchId)}/exports`, {
      method: 'POST',
      body: {},
      idempotencyKey: key,
      schema: S.ExportCreated,
    })
  },
  getExport(id: string, signal?: AbortSignal) {
    return request(`/exports/${encodeURIComponent(id)}`, { schema: S.ExportStatus, signal })
  },
  referenceData(type: string, signal?: AbortSignal) {
    return request(`/reference-data/${encodeURIComponent(type)}`, { schema: S.ReferenceData, signal })
  },
}
