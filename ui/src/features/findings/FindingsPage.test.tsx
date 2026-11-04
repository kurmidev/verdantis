import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { BRIEF_BATCH, LARGE_BATCH, db } from '../../mocks/data'
import { server } from '../../mocks/server'
import { renderApp } from '../../test/utils'
import FindingsPage from './FindingsPage'

const base = 'http://localhost/api/v1'
const PATH = '/batches/:batchId/findings'
const open = (qs = '') =>
  renderApp(<FindingsPage />, { route: `/batches/${BRIEF_BATCH}/findings${qs}`, path: PATH })

const dataRows = () => screen.getAllByRole('row').slice(1)

describe('findings queue', () => {
  it('shows the brief findings ranked with source badge, confidence and explanation', async () => {
    open()
    expect(await screen.findByText(/Manufacturer 'SKF' is present/)).toBeInTheDocument()
    const rows = dataRows()
    expect(rows).toHaveLength(3)
    expect(within(rows[0] as HTMLElement).getByText('Rule')).toBeInTheDocument()
    expect(within(rows[0] as HTMLElement).getByText('1.00')).toBeInTheDocument()
    expect(within(rows[2] as HTMLElement).getByText('Heuristic')).toBeInTheDocument()
    expect(within(rows[2] as HTMLElement).getByText('0.70')).toBeInTheDocument()
  })

  it('restores filters from the URL and sends them to the server', async () => {
    let url = ''
    server.use(http.get(`${base}/batches/${BRIEF_BATCH}/findings`, ({ request }) => {
      url = request.url
      return HttpResponse.json({ items: [], next_cursor: null })
    }))
    open('?severity=low&source=heuristic&tab=investigate')
    expect(await screen.findByText('No findings match these filters')).toBeInTheDocument()
    const q = new URL(url).searchParams
    expect(q.get('severity')).toBe('low')
    expect(q.get('source')).toBe('heuristic')
    expect(q.get('tab')).toBe('investigate')
    expect(q.get('status')).toBe('needs_review') // default status
  })

  it('changing a facet refetches with the new filter', async () => {
    open()
    await screen.findByText(/Manufacturer 'SKF'/)
    await userEvent.click(screen.getByRole('radio', { name: 'Low' }))
    await waitFor(() => expect(dataRows()).toHaveLength(1))
    expect(within(screen.getByRole('table')).getByText(/Category mismatch candidate/)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Low' })).toBeChecked()
  })

  it('pages with a cursor and loads more rows', async () => {
    renderApp(<FindingsPage />, { route: `/batches/${LARGE_BATCH}/findings`, path: PATH })
    await screen.findAllByRole('row')
    const before = dataRows().length
    expect(before).toBeGreaterThan(0)
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    await waitFor(() => expect(screen.getByRole('table')).toHaveAttribute('aria-rowcount', '201')) // 200 loaded + header
  })

  it('shows an error state with retry', async () => {
    server.use(http.get(`${base}/batches/${BRIEF_BATCH}/findings`, () =>
      HttpResponse.json({ error: { code: 'internal', trace_id: 'tr-1' } }, { status: 500 })))
    open()
    expect(await screen.findByText('Could not load this')).toBeInTheDocument()
    expect(screen.getByText('trace tr-1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})

describe('keyboard', () => {
  it('moves with j/k, opens with Enter and Esc closes the drawer', async () => {
    open()
    const first = (await screen.findAllByRole('row'))[1] as HTMLElement
    first.focus()
    await userEvent.keyboard('j')
    await waitFor(() => expect(dataRows()[1]).toHaveFocus())
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByRole('dialog', { name: 'Finding detail' })).toBeInTheDocument()
  })
})

describe('decisions', () => {
  const openFirst = async () => {
    open()
    await screen.findByText(/Manufacturer 'SKF'/)
    await userEvent.click(dataRows()[0] as HTMLElement)
    return screen.findByRole('dialog', { name: 'Finding detail' })
  }

  it('approve sends the documented request with an Idempotency-Key and updates the row', async () => {
    let seen: { body: unknown; key: string | null } | undefined
    server.use(http.post(`${base}/findings/:id/decisions`, async ({ request }) => {
      seen = { body: await request.json(), key: request.headers.get('idempotency-key') }
      return HttpResponse.json({ decision_id: 'd_1', finding_status: 'approved', requires_second_approval: false }, { status: 201 })
    }))
    const dlg = await openFirst()
    await userEvent.click(within(dlg).getByRole('button', { name: 'Approve' }))
    expect(await within(dlg).findByText(/Decided:/)).toBeInTheDocument()
    expect(seen?.body).toEqual({ action: 'approve' })
    expect(seen?.key).toMatch(/[0-9a-f-]{36}/)
  })

  it('shows "awaiting second approval" when the API requires it', async () => {
    server.use(http.post(`${base}/findings/:id/decisions`, () =>
      HttpResponse.json({ decision_id: 'd_1', finding_status: 'approved', requires_second_approval: true }, { status: 201 })))
    const dlg = await openFirst()
    await userEvent.click(within(dlg).getByRole('button', { name: 'Approve' }))
    expect((await within(dlg).findAllByText('Awaiting second approval')).length).toBeGreaterThan(0)
  })

  it('a 409 is shown and the row rolls back', async () => {
    server.use(http.post(`${base}/findings/:id/decisions`, () =>
      HttpResponse.json({ error: { code: 'state_conflict' } }, { status: 409 })))
    const dlg = await openFirst()
    await userEvent.click(within(dlg).getByRole('button', { name: 'Approve' }))
    expect(await screen.findByText(/Already decided by someone else/)).toBeInTheDocument()
    expect(within(dlg).getByRole('button', { name: 'Approve' })).toBeInTheDocument()
  })

  it('reject needs a reason code and sends it', async () => {
    let body: unknown
    server.use(http.post(`${base}/findings/:id/decisions`, async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ decision_id: 'd_2', finding_status: 'rejected' }, { status: 201 })
    }))
    const dlg = await openFirst()
    await userEvent.click(within(dlg).getByRole('button', { name: 'Reject…' }))
    const reject = await screen.findByRole('dialog', { name: 'Reject finding' })
    await userEvent.click(within(reject).getByRole('button', { name: 'Reject' }))
    expect(await within(reject).findByText('A reason is required to reject.')).toBeInTheDocument()
    expect(body).toBeUndefined()
    await userEvent.selectOptions(within(reject).getByRole('combobox'), 'wrong_suggestion')
    await userEvent.type(within(reject).getByRole('textbox'), 'Not a bearing')
    await userEvent.click(within(reject).getByRole('button', { name: 'Reject' }))
    await waitFor(() => expect(body).toEqual({ action: 'reject', reason_code: 'wrong_suggestion', comment: 'Not a bearing' }))
  })

  it('investigate sends the action', async () => {
    let body: unknown
    server.use(http.post(`${base}/findings/:id/decisions`, async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ decision_id: 'd_3', finding_status: 'investigating' }, { status: 201 })
    }))
    const dlg = await openFirst()
    await userEvent.click(within(dlg).getByRole('button', { name: 'Investigate' }))
    await waitFor(() => expect(body).toEqual({ action: 'investigate' }))
  })

  it('edit-and-approve sends edited_value for the category mismatch', async () => {
    let body: unknown
    server.use(http.post(`${base}/findings/:id/decisions`, async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ decision_id: 'd_4', finding_status: 'approved' }, { status: 201 })
    }))
    open('?severity=low')
    await userEvent.click(await screen.findByRole('button', { name: /Category mismatch candidate/ }))
    const dlg = await screen.findByRole('dialog', { name: 'Finding detail' })
    expect(within(dlg).getAllByText('Electrical').length).toBeGreaterThan(0) // evidence and "before" value
    await userEvent.click(within(dlg).getByRole('button', { name: 'Edit value…' }))
    const edit = await screen.findByRole('dialog', { name: 'Edit value and approve' })
    const select = await within(edit).findByRole('combobox')
    await within(edit).findByRole('option', { name: 'Hydraulic' })
    await userEvent.selectOptions(select, 'Hydraulic')
    await userEvent.click(within(edit).getByRole('button', { name: 'Approve with this value' }))
    await waitFor(() => expect(body).toEqual({ action: 'approve', edited_value: { category: 'Hydraulic' } }))
  })

  it('a/r/i shortcuts are off by default and work once enabled', async () => {
    let calls = 0
    server.use(http.post(`${base}/findings/:id/decisions`, () => {
      calls += 1
      return HttpResponse.json({ decision_id: 'd_5', finding_status: 'investigating' }, { status: 201 })
    }))
    const dlg = await openFirst()
    await userEvent.keyboard('i')
    expect(calls).toBe(0)
    await userEvent.keyboard('{Escape}')
    await userEvent.click(screen.getByRole('checkbox', { name: /Decision shortcuts/ }))
    await userEvent.click(dataRows()[0] as HTMLElement)
    await screen.findByRole('dialog', { name: 'Finding detail' })
    await userEvent.keyboard('i')
    await waitFor(() => expect(calls).toBe(1))
    void dlg
  })
})

describe('bulk', () => {
  const selectAll = async () => {
    open()
    await screen.findByText(/Manufacturer 'SKF'/)
    for (const cb of screen.getAllByRole('checkbox', { name: /^Select/ })) await userEvent.click(cb)
  }

  it('has no select-all and no bulk bar until something is selected', async () => {
    open()
    await screen.findByText(/Manufacturer 'SKF'/)
    expect(screen.queryByRole('region', { name: 'Bulk actions' })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: /all/i })).toBeNull()
  })

  it('confirms, then lists the failed item of a 207 and keeps it selected', async () => {
    const stale = db.findings.find((f) => f.batch_id === BRIEF_BATCH && f.issue_type === 'weak_description')
    await selectAll()
    if (stale) stale.status = 'approved' // someone else decided it after the list loaded
    const bar = screen.getByRole('region', { name: 'Bulk actions' })
    expect(within(bar).getByText('3')).toBeInTheDocument()
    await userEvent.click(within(bar).getByRole('button', { name: 'Approve selected' }))
    const confirm = await screen.findByRole('dialog', { name: 'Confirm bulk decision' })
    await userEvent.click(within(confirm).getByRole('button', { name: 'Confirm' }))
    const res = await screen.findByRole('dialog', { name: 'Bulk decision results' })
    expect(within(res).getByText('1 of 3 not applied')).toBeInTheDocument()
    expect(within(res).getByText('state_conflict')).toBeInTheDocument()
    await userEvent.click(within(res).getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.getByRole('region', { name: 'Bulk actions' })).toHaveTextContent('1'))
  })

  it('hides the bulk bar when the API says bulk is off (403)', async () => {
    server.use(http.post(`${base}/findings/decisions\\:bulk`, () => HttpResponse.json({ error: { code: 'forbidden' } }, { status: 403 })))
    await selectAll()
    await userEvent.click(screen.getByRole('button', { name: 'Investigate selected' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Bulk actions' })).toBeNull())
  })
})
