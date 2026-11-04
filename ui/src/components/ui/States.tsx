import type { ReactNode } from 'react'
import { ApiError, describeError } from '../../lib/api/errors'

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state-block">
      <h2 className="state-title">{title}</h2>
      {children}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="state-block state-error" role="alert">
      <h2 className="state-title">Could not load this</h2>
      <p>{describeError(error)}</p>
      {error instanceof ApiError && error.traceId && <p className="mono small">trace {error.traceId}</p>}
      {onRetry && <button type="button" className="btn" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Skeleton({ rows = 5, label = 'Loading' }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton-row" />)}
    </div>
  )
}
