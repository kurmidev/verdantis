import { useEffect, useState } from 'react'
import { StatusChip } from '../../components/ui/Badges'
import { useIntentKeys } from '../../hooks/useIdempotencyKey'
import type { ClientFinding, DecisionBody } from '../../lib/api/schemas'
import { EditValueForm, isEditable } from './EditValueForm'
import { RejectDialog } from './RejectDialog'
import { useDecision } from './useDecision'
import './decisions.css'

interface Props {
  finding: ClientFinding
  batchId: string
  shortcuts: boolean
}

export function DecisionPanel({ finding, batchId, shortcuts }: Props) {
  const decision = useDecision(batchId)
  const keyFor = useIntentKeys()
  const [rejecting, setRejecting] = useState(false)
  const [editing, setEditing] = useState(false)
  const open = finding.status === 'needs_review'

  const send = (body: DecisionBody) => {
    // Retrying the same body reuses its key; a changed body gets a new one (LLD 13 3.5).
    const key = keyFor(`${finding.finding_id}|${JSON.stringify(body)}`)
    decision.mutate({ findingId: finding.finding_id, body, key })
  }

  useEffect(() => {
    if (!shortcuts || !open || rejecting || editing) return
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target as HTMLElement
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)) return
      if (e.key === 'a') send({ action: 'approve' })
      else if (e.key === 'i') send({ action: 'investigate' })
      else if (e.key === 'r') setRejecting(true)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })

  if (!open) return <p className="decided">Decided: <StatusChip status={finding.status} awaiting={!!finding.awaiting_second_approval} /></p>

  const busy = decision.isPending
  return (
    <div className="decision-panel" role="group" aria-label="Decision">
      <button type="button" className="btn btn-primary" disabled={busy} onClick={() => send({ action: 'approve' })}>
        Approve
      </button>
      <button
        type="button"
        className="btn"
        disabled={busy || !isEditable(finding.issue_type)}
        aria-disabled={!isEditable(finding.issue_type)}
        title={isEditable(finding.issue_type) ? undefined : 'No editable value for this issue type'}
        onClick={() => setEditing(true)}
      >
        Edit value…
      </button>
      <button type="button" className="btn" disabled={busy} onClick={() => send({ action: 'investigate' })}>Investigate</button>
      <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setRejecting(true)}>Reject…</button>
      <RejectDialog
        open={rejecting}
        onClose={() => setRejecting(false)}
        onSubmit={(reason, comment) => {
          setRejecting(false)
          send({ action: 'reject', reason_code: reason, ...(comment ? { comment } : {}) })
        }}
      />
      <EditValueForm
        open={editing}
        finding={finding}
        onClose={() => setEditing(false)}
        onSubmit={(edited) => {
          setEditing(false)
          send({ action: 'approve', edited_value: edited })
        }}
      />
    </div>
  )
}
