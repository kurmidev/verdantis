import { useInfiniteQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui/States'
import { useLocalPref } from '../../hooks/useLocalPref'
import { useUrlState } from '../../hooks/useUrlState'
import { api, type FindingsParams } from '../../lib/api/client'
import type { ClientFinding } from '../../lib/api/schemas'
import { useBatch } from '../batches/useBatch'
import { BulkBar } from '../decisions/BulkBar'
import { FilterBar } from './FilterBar'
import { FindingDrawer } from './FindingDrawer'
import { FindingsTable } from './FindingsTable'
import './findings.css'

const KEYS = ['issue_type', 'severity', 'source', 'status', 'tab', 'finding'] as const
const PAGE = 100
const DEFAULT_STATUS = 'needs_review'

export default function FindingsPage() {
  const { batchId = '' } = useParams()
  const [u, setU] = useUrlState(KEYS)
  const batch = useBatch(batchId)
  const [shortcuts, setShortcuts] = useLocalPref('dqa.shortcuts', false) // off by default (OQ-816)
  const [bulkOff, setBulkOff] = useState(false)
  const [selection, setSelection] = useState<{ key: string; ids: Set<string> }>({ key: '', ids: new Set() })

  const status = u.status || DEFAULT_STATUS
  const filters = useMemo<FindingsParams>(
    () => ({
      issue_type: u.issue_type || undefined,
      severity: u.severity || undefined,
      source: u.source || undefined,
      status: status === 'all' ? undefined : status,
      tab: u.tab || undefined, // pass-through; the Needs-investigation tab UI is later (OQ-809)
    }),
    [u.issue_type, u.severity, u.source, u.tab, status],
  )
  const q = useInfiniteQuery({
    queryKey: ['findings', batchId, filters],
    queryFn: ({ pageParam, signal }) => api.listFindings(batchId, { ...filters, cursor: pageParam, limit: PAGE }, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  })
  const rows: ClientFinding[] = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data])
  const { hasNextPage, isFetching, isFetchingNextPage, fetchNextPage } = q
  const fetchNext = useCallback(() => void fetchNextPage(), [fetchNextPage])

  // Selection holds ids only and resets when filters change (LLD 13 3.4).
  const filterKey = JSON.stringify(filters)
  const selected = useMemo(() => (selection.key === filterKey ? selection.ids : new Set<string>()), [selection, filterKey])
  const setSelected = useCallback(
    (update: (s: Set<string>) => Set<string>) => setSelection((cur) => ({ key: filterKey, ids: update(cur.key === filterKey ? cur.ids : new Set()) })),
    [filterKey],
  )

  // Filtered view empty but more pages exist, or a deep-linked finding is not loaded yet: keep loading.
  const openRow = rows.find((r) => r.finding_id === u.finding)
  useEffect(() => {
    if (hasNextPage && !isFetching && (rows.length === 0 || (u.finding && !openRow))) fetchNext()
  }, [hasNextPage, isFetching, rows.length, u.finding, openRow, fetchNext])

  const toggle = useCallback((id: string) => setSelected((s) => {
    const n = new Set(s)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    return n
  }), [setSelected])
  const selectedRows = rows.filter((r) => selected.has(r.finding_id))
  const set = (patch: Parameters<typeof setU>[0]) => setU({ ...patch, finding: '' })

  return (
    <section aria-labelledby="h-queue" className="queue-layout">
      <aside className="rail">
        <FilterBar
          values={{ issue_type: u.issue_type, severity: u.severity, source: u.source, status }}
          issueCounts={batch.data?.findings_by_type ?? {}}
          onChange={(name, value) => set({ [name]: value })}
          onClear={() => set({ issue_type: '', severity: '', source: '', status: '', tab: '' })}
        />
        <label className="pref">
          <input type="checkbox" checked={shortcuts} onChange={(e) => setShortcuts(e.target.checked)} />
          <span>Decision shortcuts <span className="mono small">a r i</span></span>
        </label>
      </aside>

      <div className="queue-main">
        <header className="page-head">
          <div>
            <p className="eyebrow mono">{batchId}</p>
            <h1 id="h-queue" className="page-title">Review queue</h1>
          </div>
        </header>

        {batch.data?.status === 'ai_partial' && <p className="banner">AI suggestions incomplete; rule findings are complete.</p>}
        {batch.data?.ai_status === 'running' && <p className="banner" role="status">AI is still running; new findings appear as they are ready.</p>}

        {!bulkOff && (
          <BulkBar
            batchId={batchId}
            selected={selectedRows}
            onForbidden={() => setBulkOff(true)}
            onSucceeded={(ids) => setSelected((s) => new Set([...s].filter((id) => !ids.includes(id))))}
          />
        )}

        {q.isPending && <Skeleton label="Loading findings" rows={8} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.isSuccess && rows.length === 0 && !hasNextPage && (
          <EmptyState title={Object.values(filters).some(Boolean) ? 'No findings match these filters' : 'No findings'}>
            <button type="button" className="btn" onClick={() => set({ issue_type: '', severity: '', source: '', status: 'all', tab: '' })}>Clear filters</button>
          </EmptyState>
        )}
        {rows.length > 0 && (
          <FindingsTable
            rows={rows}
            selected={selected}
            hasNextPage={!!hasNextPage}
            isFetchingNext={isFetchingNextPage}
            fetchNext={fetchNext}
            onToggle={toggle}
            onOpen={(id) => setU({ finding: id })}
          />
        )}
      </div>

      <FindingDrawer
        open={!!u.finding}
        finding={openRow}
        batchId={batchId}
        shortcuts={shortcuts}
        onClose={() => setU({ finding: '' })}
      />
    </section>
  )
}
