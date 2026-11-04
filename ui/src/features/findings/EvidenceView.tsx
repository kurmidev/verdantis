import type { ClientFinding } from '../../lib/api/schemas'
import { formatValue } from '../../lib/format'

/** Raw values exactly as received, rendered as text nodes only (no HTML injection). */
export function EvidenceView({ finding }: { finding: ClientFinding }) {
  const entries = Object.entries(finding.evidence)
  const sv = finding.suggested_value ? Object.entries(finding.suggested_value) : []
  return (
    <>
      <h3 className="section-title">Evidence</h3>
      <dl className="evidence">
        {entries.map(([k, v]) => (
          <div key={k} className="evidence-row">
            <dt className="mono">{k}</dt>
            <dd className="mono evidence-hit">{formatValue(v)}</dd>
          </div>
        ))}
      </dl>
      {sv.length > 0 && (
        <>
          <h3 className="section-title">Suggested change</h3>
          <ul className="change">
            {sv.map(([k, v]) => (
              <li key={k}>
                <span className="mono">{k}</span>
                <span className="mono before">{formatValue(finding.evidence[k])}</span>
                <span aria-label="becomes">→</span>
                <span className="mono after">{formatValue(v)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}
