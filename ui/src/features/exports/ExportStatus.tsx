import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ErrorState, Skeleton } from '../../components/ui/States'
import { api } from '../../lib/api/client'
import { pollDelay } from '../batches/useBatch'

export default function ExportStatus() {
  const { batchId = '', exportId = '' } = useParams()
  const q = useQuery({
    queryKey: ['export', exportId],
    queryFn: ({ signal }) => api.getExport(exportId, signal),
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'ready' || s === 'failed' ? false : pollDelay(query.state.dataUpdateCount)
    },
  })
  if (q.isPending) return <Skeleton label="Loading export" />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  const e = q.data
  return (
    <section aria-labelledby="h-export">
      <p className="eyebrow">Export</p>
      <h1 id="h-export" className="page-title mono-title">{exportId}</h1>
      {(e.status === 'queued' || e.status === 'running') && <p role="status" className="banner">Preparing the change file… this page updates by itself.</p>}
      {e.status === 'failed' && <p role="alert" className="banner banner-error">The export failed. Go back and start it again.</p>}
      {e.status === 'ready' && e.finding_count === 0 && (
        <p className="banner">No approved findings yet, so the change file is empty. Approve findings in the review queue first.</p>
      )}
      {e.status === 'ready' && e.signed_url && (e.finding_count ?? 1) > 0 && (
        <p>
          <a className="btn btn-primary" href={e.signed_url} rel="noopener noreferrer">Download change file</a>
          <span className="small"> {e.finding_count} approved findings · link expires {e.expires_at ? new Date(e.expires_at).toLocaleTimeString() : 'soon'}</span>
        </p>
      )}
      <p><Link to={`/batches/${batchId}`}>Back to batch</Link></p>
    </section>
  )
}
