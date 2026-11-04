import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import type { ClientFinding, FindingsPage } from '../../lib/api/schemas'

type Pages = InfiniteData<FindingsPage>
export type Snapshot = [readonly unknown[], Pages | undefined][]

const key = (batchId: string) => ['findings', batchId] as const

export function snapshot(qc: QueryClient, batchId: string): Snapshot {
  return qc.getQueriesData<Pages>({ queryKey: key(batchId) })
}
export function restore(qc: QueryClient, snap: Snapshot): void {
  for (const [k, v] of snap) qc.setQueryData(k, v)
}

/** Patch rows by id across every cached filter variant (server state stays in the query cache). */
export function patchFindings(qc: QueryClient, batchId: string, patches: Map<string, Partial<ClientFinding>>): void {
  qc.setQueriesData<Pages>({ queryKey: key(batchId) }, (old) =>
    old && {
      ...old,
      pages: old.pages.map((p) => ({ ...p, items: p.items.map((f) => (patches.has(f.finding_id) ? { ...f, ...patches.get(f.finding_id) } : f)) })),
    },
  )
}
