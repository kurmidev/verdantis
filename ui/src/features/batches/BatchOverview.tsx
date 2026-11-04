import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { StatusChip } from '../../components/ui/Badges'
import { ErrorState, Skeleton } from '../../components/ui/States'
import { useToast } from '../../components/ui/Toast'
import { describeBatchError } from '../../lib/api/errors'
import { issueLabel } from '../../lib/format'
import { ExportButton } from '../exports/ExportButton'
import { isSettled, useBatch } from './useBatch'
import './batches.css'

export default function BatchOverview() {
  const { batchId = '' } = useParams()
  const toast = useToast()
  const q = useBatch(batchId)
  const last = useRef<string | undefined>(undefined)
  const status = q.data?.status
  useEffect(() => {
    if (status && last.current && last.current !== status) toast(`Batch ${batchId} is now ${status}`)
    last.current = status
  }, [status, batchId, toast])

  if (q.isPending) return <Skeleton label="Loading batch" />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  const b = q.data
  const reviewable = b.status === 'done' || b.status === 'ai_partial'
  const counts = Object.entries(b.findings_by_type).sort((x, y) => y[1] - x[1])

  return (
    <section aria-labelledby="h-batch">
      <header className="page-head">
        <div>
          <p className="eyebrow">Batch</p>
          <h1 id="h-batch" className="page-title mono-title">{b.batch_id}</h1>
        </div>
        <StatusChip status={b.status} />
      </header>

      {b.status === 'empty' && <p className="banner">File contained no records.</p>}
      {b.status === 'failed' && <p className="banner banner-error" role="alert">{describeBatchError(b.error_code)}</p>}
      {b.status === 'ai_partial' && <p className="banner">AI suggestions incomplete; rule findings are complete.</p>}
      {!isSettled(b) && <p className="banner" role="status">Processing… this page updates by itself.</p>}

      <dl className="facts">
        <div><dt>File</dt><dd>{b.filename ?? '—'}</dd></div>
        <div><dt>Records</dt><dd className="tnum">{b.records ?? '—'}</dd></div>
        <div><dt>AI status</dt><dd>{b.ai_status ? issueLabel(b.ai_status) : '—'}</dd></div>
        <div><dt>Last updated</dt><dd className="tnum">{new Date(q.dataUpdatedAt).toLocaleTimeString()}</dd></div>
      </dl>

      {counts.length > 0 && (
        <>
          <h2 className="section-title">Findings by type</h2>
          <ul className="counts">
            {counts.map(([type, n]) => (
              <li key={type}><span>{issueLabel(type)}</span><span className="tnum">{n}</span></li>
            ))}
          </ul>
        </>
      )}

      <div className="actions">
        {reviewable && <Link className="btn btn-primary" to={`/batches/${b.batch_id}/findings`}>Review findings</Link>}
        {reviewable && <ExportButton batchId={b.batch_id} />}
      </div>
    </section>
  )
}
