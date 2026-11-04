export class ApiError extends Error {
  status: number
  code: string
  traceId: string | undefined
  details: unknown
  retryAfter: number | undefined

  constructor(
    status: number,
    code: string,
    message: string,
    extra: { traceId?: string; details?: unknown; retryAfter?: number } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.traceId = extra.traceId
    this.details = extra.details
    this.retryAfter = extra.retryAfter
  }
}

/** Plain-language mapping of the error taxonomy (LLD 13 3.14). */
export function describeError(e: unknown): string {
  if (!(e instanceof ApiError)) return 'Something went wrong. Please try again.'
  const trace = e.traceId ? ` (trace ${e.traceId})` : ''
  switch (true) {
    case e.status === 401:
      return 'Your session has expired. Sign in again.'
    case e.status === 403:
      return 'You are not allowed to do this.'
    case e.status === 404:
      return 'Not found.'
    case e.status === 409:
      return 'Already decided by someone else, or no longer open.'
    case e.status === 413:
      return 'The file is too large. Split it into smaller files and upload again.'
    case e.status === 422 && e.code === 'idempotency_conflict':
      return `The request could not be completed${trace}.`
    case e.status === 422:
      return e.message || 'The request was not valid.'
    case e.status === 429:
      return `Too many requests. Try again in ${e.retryAfter ?? 'a few'} seconds.`
    case e.status === 0:
      return 'Network error. Check your connection and retry.'
    default:
      return `The service had a problem${trace}. Please retry.`
  }
}

const BATCH_ERRORS: Record<string, string> = {
  too_many_rows: 'The file has more than 100,000 rows. Split it into smaller files and upload again.',
  parse_error: 'The file could not be read. Check the format and encoding, then upload again.',
  timeout: 'Processing took too long. Try again or split the file.',
}
export const describeBatchError = (code: string | null | undefined): string =>
  (code && BATCH_ERRORS[code]) || 'Processing failed. Contact the data platform team with the batch id.'
