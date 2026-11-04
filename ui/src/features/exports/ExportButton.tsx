import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../../components/ui/Toast'
import { api, newKey } from '../../lib/api/client'
import { describeError } from '../../lib/api/errors'

export function ExportButton({ batchId }: { batchId: string }) {
  const nav = useNavigate()
  const toast = useToast()
  const m = useMutation({
    // A new click is a new intent (later approvals must be included), so a fresh key each time.
    mutationFn: () => api.createExport(batchId, newKey()),
    onSuccess: (r) => nav(`/batches/${batchId}/exports/${r.export_id}`),
    onError: (e) => toast(describeError(e), 'error'),
  })
  return (
    <button type="button" className="btn" disabled={m.isPending} onClick={() => m.mutate()}>
      {m.isPending ? 'Starting export…' : 'Export approved changes'}
    </button>
  )
}
