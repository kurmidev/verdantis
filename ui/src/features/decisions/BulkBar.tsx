import { useState } from 'react'
import { Dialog } from '../../components/ui/Dialog'
import { useToast } from '../../components/ui/Toast'
import { useIntentKeys } from '../../hooks/useIdempotencyKey'
import { ApiError, describeError } from '../../lib/api/errors'
import type { BulkItem, BulkResult, ClientFinding, DecisionAction } from '../../lib/api/schemas'
import { RejectDialog } from './RejectDialog'
import { useBulkDecision } from './useDecision'
import './decisions.css'

const MAX_BULK = 500 // LLD 04
const VERB: Record<DecisionAction, string> = { approve: 'Approve', reject: 'Reject', investigate: 'Investigate' }

interface Props {
  batchId: string
  selected: ClientFinding[]
  onSucceeded: (ids: string[]) => void
  onForbidden: () => void
}

export function BulkBar({ batchId, selected, onSucceeded, onForbidden }: Props) {
  const bulk = useBulkDecision(batchId)
  const toast = useToast()
  const keyFor = useIntentKeys()
  const [confirm, setConfirm] = useState<{ action: DecisionAction; reason?: string; comment?: string } | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [result, setResult] = useState<BulkResult | null>(null)
  const n = selected.length
  const tooMany = n > MAX_BULK
  const ai = selected.filter((f) => f.source === 'ai_suggestion').length

  const run = () => {
    if (!confirm) return
    const items: BulkItem[] = selected.map((f) => ({
      finding_id: f.finding_id,
      action: confirm.action,
      ...(confirm.reason ? { reason_code: confirm.reason } : {}),
      ...(confirm.comment ? { comment: confirm.comment } : {}),
    }))
    const key = keyFor(JSON.stringify(items))
    setConfirm(null)
    bulk.mutate({ items, key }, {
      onSuccess: (res) => {
        onSucceeded(res.results.filter((r) => r.status === 201).map((r) => r.finding_id))
        if (res.results.some((r) => r.status !== 201)) setResult(res)
        else toast(`${res.results.length} decisions recorded.`)
      },
      onError: (e) => {
        if (e instanceof ApiError && e.status === 403) onForbidden() // flag bulk_approve_enabled off
        toast(describeError(e), 'error')
      },
    })
  }

  if (n === 0) return null
  const failed = result?.results.filter((r) => r.status !== 201) ?? []
  return (
    <div className="bulk-bar" role="region" aria-label="Bulk actions">
      <p className="bulk-count"><strong className="tnum">{n}</strong> selected{tooMany && ` (max ${MAX_BULK} per request)`}</p>
      <button type="button" className="btn btn-primary" disabled={tooMany || bulk.isPending} onClick={() => setConfirm({ action: 'approve' })}>Approve selected</button>
      <button type="button" className="btn" disabled={tooMany || bulk.isPending} onClick={() => setConfirm({ action: 'investigate' })}>Investigate selected</button>
      <button type="button" className="btn btn-danger" disabled={tooMany || bulk.isPending} onClick={() => setRejecting(true)}>Reject selected…</button>

      <RejectDialog open={rejecting} count={n} onClose={() => setRejecting(false)} onSubmit={(reason, comment) => { setRejecting(false); setConfirm({ action: 'reject', reason, comment }) }} />

      <Dialog open={!!confirm} onClose={() => setConfirm(null)} label="Confirm bulk decision">
        <div className="dialog-body">
          <h2 className="dialog-title">{confirm && VERB[confirm.action]} {n} findings?</h2>
          <p>Each finding is decided on its own; some may fail if someone else already decided them.</p>
          {confirm?.action === 'approve' && ai > 0 && <p className="banner">{ai} of these are AI suggestions. Check them before approving.</p>}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => setConfirm(null)}>Cancel</button>
            <button type="button" className="btn btn-primary" onClick={run}>Confirm</button>
          </div>
        </div>
      </Dialog>

      <Dialog open={!!result} onClose={() => setResult(null)} label="Bulk decision results">
        <div className="dialog-body">
          <h2 className="dialog-title">{failed.length} of {result?.results.length} not applied</h2>
          <ul className="fail-list">
            {failed.map((r) => (
              <li key={r.finding_id}><span className="mono">{r.finding_id}</span> <span>{r.error?.code ?? `status ${r.status}`}</span></li>
            ))}
          </ul>
          <p className="small">The other findings were updated. Failed items stay selected.</p>
          <div className="dialog-actions"><button type="button" className="btn btn-primary" onClick={() => setResult(null)}>Close</button></div>
        </div>
      </Dialog>
    </div>
  )
}
