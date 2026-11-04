import type { Batch, Finding } from '../lib/api/schemas'

export const BRIEF_BATCH = 'b_01J9ZK2A7T'
export const LARGE_BATCH = 'b_large_demo'
export const RUNNING_BATCH = 'b_running_demo'
export const FAILED_BATCH = 'b_failed_demo'
export const EMPTY_BATCH = 'b_empty_demo'

interface MockExport {
  status: string
  finding_count: number
  polls: number
}
interface Db {
  batches: Batch[]
  findings: Finding[]
  exports: Map<string, MockExport>
  runningPolls: number
  idempotency: Map<string, unknown>
}

const base = {
  also_detected_by: [] as string[],
  model_id: null,
  prompt_version: null,
  status: 'needs_review',
  created_at: '2026-11-04T09:00:00Z',
}

// Provisional outputs of the implemented checks for the brief sample (OQ-12, OQ-19, OQ-130).
const briefFindings = (): Finding[] => [
  {
    ...base,
    finding_id: 'f_01J9ZK3M8Q',
    batch_id: BRIEF_BATCH,
    record_key: 'ERP-A:1001',
    item_id: '1001',
    issue_type: 'missing_part_number',
    severity: 'medium',
    confidence: 1.0,
    explanation: "Manufacturer 'SKF' is present but manufacturer part number is blank.",
    evidence: { manufacturer: 'SKF', manufacturer_part_number: '' },
    suggested_action: 'Request manufacturer part number from the source owner.',
    suggested_value: null,
    source: 'deterministic_rule',
    rule_id: 'missing_part_number',
    rule_version: '1.0.0',
  },
  {
    ...base,
    finding_id: 'f_01J9ZK3N2B',
    batch_id: BRIEF_BATCH,
    record_key: 'ERP-A:1001',
    item_id: '1001',
    issue_type: 'weak_description',
    severity: 'medium',
    confidence: 0.9,
    explanation: "Description 'bearing' has fewer than 3 tokens and no attribute tokens.",
    evidence: { item_description: 'bearing', tokens: 1 },
    suggested_action: 'Ask the source owner for a fuller description (type, size, standard).',
    suggested_value: null,
    source: 'heuristic',
    rule_id: 'weak_description',
    rule_version: '1.0.0',
  },
  {
    ...base,
    finding_id: 'f_01J9ZK3P4R',
    batch_id: BRIEF_BATCH,
    record_key: 'ERP-B:1002',
    item_id: '1002',
    issue_type: 'category_mismatch_candidate',
    severity: 'low',
    confidence: 0.7,
    explanation: 'Description suggests a mechanical bearing, but category is Electrical.',
    evidence: { item_description: 'SKF Bearing 6205 ZZ', category: 'Electrical', keyword: 'bearing' },
    suggested_action: 'Review category assignment before approval.',
    suggested_value: { category: 'Mechanical' },
    source: 'heuristic',
    rule_id: 'category_mismatch',
    rule_version: '1.2.0',
  },
]

const TYPES = ['unsupported_uom', 'category_mismatch_candidate', 'possible_duplicate', 'weak_description']
const SEVS = ['high', 'medium', 'low']
const SOURCES = ['deterministic_rule', 'heuristic', 'ai_suggestion']

export const largeFindings = (n = 240): Finding[] =>
  Array.from({ length: n }, (_, i) => {
    const issue = TYPES[i % TYPES.length] as string
    const source = issue === 'unsupported_uom' ? 'deterministic_rule' : (SOURCES[(i % 2) + 1] as string)
    return {
      ...base,
      finding_id: `f_large_${String(i).padStart(4, '0')}`,
      batch_id: LARGE_BATCH,
      record_key: `ERP-C:${2000 + i}`,
      item_id: String(2000 + i),
      issue_type: issue,
      severity: SEVS[(i * 7) % 3] as string,
      confidence: Number((1 - ((i * 13) % 50) / 100).toFixed(2)),
      explanation: `Synthetic finding ${i} for ${issue.replaceAll('_', ' ')} with a deliberately long explanation to test truncation at narrow widths.`,
      evidence: { item_description: `Part ${i}`, unit_of_measure: i % 5 === 0 ? 'EACH' : '', category: 'Mechanical' },
      suggested_action: 'Review with the source owner.',
      suggested_value: issue === 'unsupported_uom' ? { unit_of_measure: 'EA' } : null,
      source,
      model_id: source === 'ai_suggestion' ? 'mock-mid' : null,
      prompt_version: source === 'ai_suggestion' ? 'category/v1' : null,
      rule_id: issue,
      rule_version: '1.0.0',
    }
  })

const batches = (): Batch[] => [
  {
    batch_id: BRIEF_BATCH,
    status: 'done',
    records: 2,
    findings_by_type: { missing_part_number: 1, weak_description: 1, category_mismatch_candidate: 1 },
    ai_status: 'skipped',
    created_at: '2026-11-04T09:00:00Z',
    completed_at: '2026-11-04T09:00:07Z',
    filename: 'brief-sample-input.json',
  },
  {
    batch_id: LARGE_BATCH,
    status: 'ai_partial',
    records: 5000,
    findings_by_type: { unsupported_uom: 60, category_mismatch_candidate: 60, possible_duplicate: 60, weak_description: 60 },
    ai_status: 'partial',
    created_at: '2026-11-03T14:20:00Z',
    completed_at: '2026-11-03T14:21:40Z',
    filename: 'erp-c-items.csv',
  },
  {
    batch_id: RUNNING_BATCH,
    status: 'processing',
    records: 1200,
    findings_by_type: {},
    ai_status: 'running',
    created_at: '2026-11-04T10:00:00Z',
    filename: 'erp-d-items.json',
  },
  {
    batch_id: FAILED_BATCH,
    status: 'failed',
    records: 0,
    findings_by_type: {},
    ai_status: 'skipped',
    error_code: 'too_many_rows',
    created_at: '2026-11-02T08:00:00Z',
    filename: 'huge.csv',
  },
  {
    batch_id: EMPTY_BATCH,
    status: 'empty',
    records: 0,
    findings_by_type: {},
    ai_status: 'skipped',
    created_at: '2026-11-02T07:00:00Z',
    filename: 'empty.json',
  },
]

export let db: Db = fresh()

function fresh(): Db {
  return {
    batches: batches(),
    findings: [...briefFindings(), ...largeFindings()],
    exports: new Map(),
    runningPolls: 0,
    idempotency: new Map(),
  }
}

export function resetDb(): void {
  db = fresh()
}
