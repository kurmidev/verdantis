import { createColumnHelper, flexRender, getCoreRowModel, useReactTable, type RowData } from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { ConfidenceMeter, SeverityTag, SourceBadge, StatusChip } from '../../components/ui/Badges'
import type { ClientFinding } from '../../lib/api/schemas'
import { issueLabel } from '../../lib/format'
import './findings.css'

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface TableMeta<TData extends RowData> {
    selected: Set<string>
    toggle: (id: string) => void
    open: (id: string) => void
      _row?: TData
  }
}

const ROW_H = 44 // >= 44 px touch target (web rules)
const PREFETCH_AT = 20 // fetch the next page when the last 20 rows come into view
const h = createColumnHelper<ClientFinding>()

const columns = [
  h.display({
    id: 'select',
    header: () => <span className="visually-hidden">Select</span>,
    cell: ({ row, table }) => {
      const m = table.options.meta
      if (!m) return null
      const open = row.original.status === 'needs_review'
      return (
        <input
          type="checkbox"
          aria-label={`Select ${issueLabel(row.original.issue_type)} for ${row.original.record_key}`}
          checked={m.selected.has(row.id)}
          disabled={!open}
          onChange={() => m.toggle(row.id)}
          onClick={(e) => e.stopPropagation()}
        />
      )
    },
  }),
  h.accessor('severity', { header: 'Severity', cell: (c) => <SeverityTag severity={c.getValue()} /> }),
  h.accessor('issue_type', {
    header: 'Issue',
    cell: ({ row, table }) => (
      <button type="button" className="row-open" onClick={(e) => { e.stopPropagation(); table.options.meta?.open(row.id) }}>
        {issueLabel(row.original.issue_type)}
        <span className="mono row-key"> {row.original.record_key}</span>
      </button>
    ),
  }),
  h.accessor('explanation', { header: 'Explanation', cell: (c) => <span className="clip" title={c.getValue()}>{c.getValue()}</span> }),
  h.accessor('source', { header: 'Source', cell: (c) => <SourceBadge source={c.getValue()} /> }),
  h.accessor('confidence', { header: 'Confidence', cell: (c) => <ConfidenceMeter value={c.getValue()} /> }),
  h.accessor('status', { header: 'Status', cell: ({ row }) => <StatusChip status={row.original.status} awaiting={!!row.original.awaiting_second_approval} /> }),
]

interface Props {
  rows: ClientFinding[]
  selected: Set<string>
  hasNextPage: boolean
  isFetchingNext: boolean
  fetchNext: () => void
  onToggle: (id: string) => void
  onOpen: (id: string) => void
}

export function FindingsTable({ rows, selected, hasNextPage, isFetchingNext, fetchNext, onToggle, onOpen }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(0)
  const keyboardMoved = useRef(false)
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (r) => r.finding_id,
    meta: { selected, toggle: onToggle, open: onOpen },
  })
  const tableRows = table.getRowModel().rows
  const virt = useVirtualizer({ count: tableRows.length, getScrollElement: () => scrollRef.current, estimateSize: () => ROW_H, overscan: 10 })
  const items = virt.getVirtualItems()
  const padTop = items[0]?.start ?? 0
  const padBottom = items.length ? virt.getTotalSize() - (items[items.length - 1]?.end ?? 0) : 0
  const lastIndex = items[items.length - 1]?.index ?? -1
  const activeIdx = Math.min(active, Math.max(0, tableRows.length - 1))
  const colCount = columns.length

  useEffect(() => {
    if (hasNextPage && !isFetchingNext && lastIndex >= tableRows.length - PREFETCH_AT) fetchNext()
  }, [lastIndex, tableRows.length, hasNextPage, isFetchingNext, fetchNext])

  useEffect(() => {
    if (!keyboardMoved.current) return
    keyboardMoved.current = false
    scrollRef.current?.querySelector<HTMLElement>(`[data-index="${activeIdx}"]`)?.focus()
  }, [activeIdx, lastIndex])

  const move = (i: number) => {
    const next = Math.max(0, Math.min(tableRows.length - 1, i))
    keyboardMoved.current = true
    setActive(next)
    virt.scrollToIndex(next)
  }
  const onKeyDown = (e: KeyboardEvent<HTMLTableRowElement>, i: number, id: string) => {
    if (e.target !== e.currentTarget || e.metaKey || e.ctrlKey || e.altKey) return
    if (e.key === 'j' || e.key === 'ArrowDown') move(i + 1)
    else if (e.key === 'k' || e.key === 'ArrowUp') move(i - 1)
    else if (e.key === 'Home') move(0)
    else if (e.key === 'End') move(tableRows.length - 1)
    else if (e.key === 'Enter') onOpen(id)
    else if (e.key === ' ' && rows[i]?.status === 'needs_review') onToggle(id)
    else return
    e.preventDefault()
  }

  const headers = useMemo(() => table.getHeaderGroups()[0]?.headers ?? [], [table])
  return (
    <div className="queue-scroll" ref={scrollRef}>
      <table className="ledger queue" aria-label="Findings" aria-rowcount={tableRows.length + 1}>
        <thead>
          <tr aria-rowindex={1}>
            {headers.map((hd) => (
              <th key={hd.id} scope="col" className={hd.id === 'confidence' ? 'num' : undefined}>
                {flexRender(hd.column.columnDef.header, hd.getContext())}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {padTop > 0 && <tr aria-hidden="true" style={{ height: padTop }}><td colSpan={colCount} /></tr>}
          {items.map((vi) => {
            const row = tableRows[vi.index]
            if (!row) return null
            const sel = selected.has(row.id)
            return (
              <tr
                key={row.id}
                data-index={vi.index}
                aria-rowindex={vi.index + 2}
                aria-selected={sel}
                tabIndex={vi.index === activeIdx ? 0 : -1}
                className={`qrow${sel ? ' is-selected' : ''}${row.original.pending ? ' is-pending' : ''}`}
                style={{ height: ROW_H }}
                onClick={() => onOpen(row.id)}
                onFocus={() => setActive(vi.index)}
                onKeyDown={(e) => onKeyDown(e, vi.index, row.id)}
              >
                {row.getVisibleCells().map((c) => (
                  <td key={c.id}>{flexRender(c.column.columnDef.cell, c.getContext())}</td>
                ))}
              </tr>
            )
          })}
          {padBottom > 0 && <tr aria-hidden="true" style={{ height: padBottom }}><td colSpan={colCount} /></tr>}
        </tbody>
      </table>
      {hasNextPage && (
        <p className="load-more">
          <button type="button" className="btn" disabled={isFetchingNext} onClick={fetchNext}>
            {isFetchingNext ? 'Loading…' : 'Load more'}
          </button>
        </p>
      )}
    </div>
  )
}
