import { issueLabel } from '../../lib/format'
import './findings.css'

interface Facet {
  name: 'issue_type' | 'severity' | 'source' | 'status'
  legend: string
  options: { value: string; label: string; count?: number | undefined }[]
}

interface Props {
  values: Record<Facet['name'], string>
  issueCounts: Record<string, number>
  onChange: (name: Facet['name'], value: string) => void
  onClear: () => void
}

const SEVERITIES = ['high', 'medium', 'low']
const SOURCES = [['deterministic_rule', 'Rule'], ['heuristic', 'Heuristic'], ['ai_suggestion', 'AI']] as const
const STATUSES = ['needs_review', 'investigating', 'approved', 'rejected']

/** Filters as typographic facets with live counts (LLD 13 3.10); all server-side. */
export function FilterBar({ values, issueCounts, onChange, onClear }: Props) {
  const facets: Facet[] = [
    { name: 'status', legend: 'Status', options: [...STATUSES.map((s) => ({ value: s, label: issueLabel(s) })), { value: 'all', label: 'All' }] },
    { name: 'issue_type', legend: 'Issue', options: [{ value: '', label: 'All issues' }, ...Object.entries(issueCounts).map(([k, n]) => ({ value: k, label: issueLabel(k), count: n }))] },
    { name: 'severity', legend: 'Severity', options: [{ value: '', label: 'Any' }, ...SEVERITIES.map((s) => ({ value: s, label: issueLabel(s) }))] },
    { name: 'source', legend: 'Source', options: [{ value: '', label: 'Any' }, ...SOURCES.map(([v, l]) => ({ value: v, label: l }))] },
  ]
  return (
    <form className="facets" aria-label="Filter findings" onSubmit={(e) => e.preventDefault()}>
      {facets.map((f) => (
        <fieldset key={f.name} className="facet">
          <legend>{f.legend}</legend>
          {f.options.map((o) => (
            <label key={o.value || 'any'} className="facet-option">
              <input type="radio" name={f.name} value={o.value} checked={values[f.name] === o.value} onChange={() => onChange(f.name, o.value)} />
              <span>{o.label}</span>
              {o.count !== undefined && <span className="tnum facet-count">{o.count}</span>}
            </label>
          ))}
        </fieldset>
      ))}
      <button type="button" className="btn btn-quiet" onClick={onClear}>Clear filters</button>
    </form>
  )
}
