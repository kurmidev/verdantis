import { formatConfidence, issueLabel, sourceLabel, statusLabel } from '../../lib/format'

const SHAPE: Record<string, string> = { deterministic_rule: 'square', heuristic: 'diamond', ai_suggestion: 'circle' }

/** Text plus shape, never colour alone (LLD 13 3.6). */
export function SourceBadge({ source, secondary = false }: { source: string; secondary?: boolean }) {
  return (
    <span className={`badge badge-${SHAPE[source] ?? 'unknown'}${secondary ? ' badge-secondary' : ''}`}>
      <span className="badge-shape" aria-hidden="true" />
      {sourceLabel(source)}
    </span>
  )
}

const SEV_ICON: Record<string, string> = { high: '▲', medium: '◆', low: '▽' }
export function SeverityTag({ severity }: { severity: string }) {
  return (
    <span className={`sev sev-${SEV_ICON[severity] ? severity : 'unknown'}`}>
      <span aria-hidden="true">{SEV_ICON[severity] ?? '•'}</span> {issueLabel(severity)}
    </span>
  )
}

export function ConfidenceMeter({ value }: { value: number }) {
  const v = Math.min(1, Math.max(0, value))
  return (
    <span className="confidence">
      <span className="tnum">{formatConfidence(value)}</span>
      <span className="meter" aria-hidden="true">
        <i style={{ transform: `scaleX(${v})` }} />
      </span>
    </span>
  )
}

export function StatusChip({ status, awaiting = false }: { status: string; awaiting?: boolean }) {
  return <span className={`chip chip-${status}`}>{awaiting ? 'Awaiting second approval' : statusLabel(status)}</span>
}
