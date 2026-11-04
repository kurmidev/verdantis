import { ConfidenceMeter, SeverityTag, SourceBadge, StatusChip } from '../../components/ui/Badges'
import { Dialog } from '../../components/ui/Dialog'
import type { ClientFinding } from '../../lib/api/schemas'
import { issueLabel } from '../../lib/format'
import { DecisionPanel } from '../decisions/DecisionPanel'
import { EvidenceView } from './EvidenceView'
import './findings.css'

interface Props {
  finding: ClientFinding | undefined
  open: boolean
  batchId: string
  shortcuts: boolean
  onClose: () => void
}

export function FindingDrawer({ finding, open, batchId, shortcuts, onClose }: Props) {
  return (
    <Dialog open={open} onClose={onClose} label="Finding detail" className="drawer">
      {finding ? (
        <article className="drawer-body" aria-labelledby="drawer-title">
          <header className="drawer-head">
            <div>
              <p className="eyebrow mono">{finding.record_key}</p>
              <h2 id="drawer-title" className="drawer-title">{issueLabel(finding.issue_type)}</h2>
            </div>
            <button type="button" className="btn btn-quiet" onClick={onClose} aria-label="Close detail">Close</button>
          </header>
          <p className="drawer-meta">
            <SeverityTag severity={finding.severity} />
            <SourceBadge source={finding.source} />
            {finding.also_detected_by.map((s) => <SourceBadge key={s} source={s} secondary />)}
            <ConfidenceMeter value={finding.confidence} />
            <StatusChip status={finding.status} awaiting={!!finding.awaiting_second_approval} />
          </p>
          <p className="explanation">{finding.explanation}</p>
          <p><strong>Suggested action:</strong> {finding.suggested_action}</p>
          <EvidenceView finding={finding} />
          <p className="small mono">
            {finding.rule_id} v{finding.rule_version}
            {finding.model_id ? ` · ${finding.model_id} · ${finding.prompt_version ?? ''}` : ''}
          </p>
          <DecisionPanel finding={finding} batchId={batchId} shortcuts={shortcuts} />
        </article>
      ) : (
        <p className="dialog-body">Loading finding…</p>
      )}
    </Dialog>
  )
}
