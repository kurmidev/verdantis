import { useState, type FormEvent } from 'react'
import { Dialog } from '../../components/ui/Dialog'

// PROVISIONAL (OQ-802, OQ-6): the HLD gives only `wrong_suggestion`; the rest are placeholders.
export const REASON_CODES = [
  ['wrong_suggestion', 'Suggestion is wrong'],
  ['not_an_issue', 'Not an issue'],
  ['insufficient_evidence', 'Insufficient evidence'],
  ['other', 'Other'],
] as const

interface Props {
  open: boolean
  count?: number
  onClose: () => void
  onSubmit: (reason: string, comment: string) => void
}

export function RejectDialog({ open, count = 1, onClose, onSubmit }: Props) {
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const [touched, setTouched] = useState(false)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!reason) return
    onSubmit(reason, comment.trim())
    setReason('')
    setComment('')
    setTouched(false)
  }
  return (
    <Dialog open={open} onClose={onClose} label="Reject finding">
      <form onSubmit={submit} noValidate className="dialog-body">
        <h2 className="dialog-title">Reject {count === 1 ? 'finding' : `${count} findings`}</h2>
        <label className="field">
          <span>Reason</span>
          <select value={reason} onChange={(e) => setReason(e.target.value)} aria-invalid={touched && !reason} aria-describedby="reason-err">
            <option value="">Choose a reason…</option>
            {REASON_CODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        {touched && !reason && <p id="reason-err" role="alert" className="field-error">A reason is required to reject.</p>}
        <label className="field">
          <span>Comment (optional)</span>
          <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-danger">Reject</button>
        </div>
      </form>
    </Dialog>
  )
}
