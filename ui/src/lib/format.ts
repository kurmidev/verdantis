export function isBlank(v: unknown): boolean {
  return v === null || v === undefined || (typeof v === 'string' && v.trim() === '')
}

/** Raw value exactly as received; blank gets an explicit marker (LLD 13 3.6). */
export function formatValue(v: unknown): string {
  if (isBlank(v)) return '(blank)'
  return typeof v === 'string' ? v : JSON.stringify(v)
}

export const formatConfidence = (n: number): string => n.toFixed(2)

export function issueLabel(t: string): string {
  const s = t.replaceAll('_', ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export const SOURCE_LABEL: Record<string, string> = {
  deterministic_rule: 'Rule',
  heuristic: 'Heuristic',
  ai_suggestion: 'AI',
}
export const sourceLabel = (s: string): string => SOURCE_LABEL[s] ?? s

export function statusLabel(s: string): string {
  return issueLabel(s)
}
