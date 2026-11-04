import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { StatusChip } from '../../components/ui/Badges'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui/States'
import { api } from '../../lib/api/client'
import './batches.css'

export default function BatchList() {
  // GET /batches is not in LLD 04 yet (OQ-810): provisional contract.
  const q = useQuery({ queryKey: ['batches'], queryFn: ({ signal }) => api.listBatches(undefined, signal) })
  return (
    <section aria-labelledby="h-batches">
      <header className="page-head">
        <h1 id="h-batches" className="page-title">Batches</h1>
        <Link className="btn btn-primary" to="/batches/new">Upload batch</Link>
      </header>
      {q.isPending && <Skeleton label="Loading batches" />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && q.data.items.length === 0 && (
        <EmptyState title="No batches yet">
          <Link className="btn" to="/batches/new">Upload the first batch</Link>
        </EmptyState>
      )}
      {q.data && q.data.items.length > 0 && (
        <table className="ledger">
          <caption className="visually-hidden">Batches</caption>
          <thead>
            <tr><th scope="col">Batch</th><th scope="col">File</th><th scope="col">Status</th><th scope="col" className="num">Records</th><th scope="col">Created</th></tr>
          </thead>
          <tbody>
            {q.data.items.map((b) => (
              <tr key={b.batch_id}>
                <td><Link className="mono" to={`/batches/${b.batch_id}`}>{b.batch_id}</Link></td>
                <td>{b.filename ?? '—'}</td>
                <td><StatusChip status={b.status} /></td>
                <td className="num tnum">{b.records ?? '—'}</td>
                <td className="tnum">{b.created_at ? new Date(b.created_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
