import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Dialog } from '../../components/ui/Dialog'
import { api } from '../../lib/api/client'
import type { ClientFinding } from '../../lib/api/schemas'
import { formatValue } from '../../lib/format'

// PROVISIONAL (OQ-803): editable field and its allowed list per issue type.
const EDITABLE: Record<string, { field: string; ref: string; label: string }> = {
  category_mismatch_candidate: { field: 'category', ref: 'taxonomy', label: 'Category' },
  unsupported_uom: { field: 'unit_of_measure', ref: 'allowed_uom', label: 'Unit of measure' },
}
export const isEditable = (issueType: string): boolean => issueType in EDITABLE

interface Props {
  open: boolean
  finding: ClientFinding
  onClose: () => void
  onSubmit: (edited: Record<string, unknown>) => void
}

export function EditValueForm({ open, finding, onClose, onSubmit }: Props) {
  const spec = EDITABLE[finding.issue_type]
  const ref = useQuery({
    queryKey: ['reference', spec?.ref],
    queryFn: ({ signal }) => api.referenceData(spec?.ref ?? '', signal),
    enabled: open && !!spec,
    staleTime: 5 * 60_000,
  })
  const suggested = spec ? finding.suggested_value?.[spec.field] : undefined
  const [value, setValue] = useState<string | null>(null)
  if (!spec) return null
  const current = value ?? (typeof suggested === 'string' ? suggested : '')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (current.trim()) onSubmit({ [spec.field]: current.trim() })
  }
  return (
    <Dialog open={open} onClose={onClose} label="Edit value and approve">
      <form onSubmit={submit} noValidate className="dialog-body">
        <h2 className="dialog-title">Edit value and approve</h2>
        <p className="small">Current: <span className="mono">{formatValue(finding.evidence[spec.field])}</span></p>
        <label className="field">
          <span>{spec.label}</span>
          {ref.data ? (
            <select value={current} onChange={(e) => setValue(e.target.value)}>
              <option value="">Choose…</option>
              {ref.data.values.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          ) : (
            <input value={current} onChange={(e) => setValue(e.target.value)} />
          )}
        </label>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={!current.trim()}>Approve with this value</button>
        </div>
      </form>
    </Dialog>
  )
}
