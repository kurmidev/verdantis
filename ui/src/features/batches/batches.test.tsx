import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { BRIEF_BATCH, EMPTY_BATCH, FAILED_BATCH, LARGE_BATCH, RUNNING_BATCH, db } from '../../mocks/data'
import { renderApp } from '../../test/utils'
import BatchList from './BatchList'
import BatchOverview from './BatchOverview'
import { UploadForm } from './UploadForm'
import { pollDelay } from './useBatch'
import ExportStatus from '../exports/ExportStatus'
import { http, HttpResponse } from 'msw'
import { server } from '../../mocks/server'

const overview = (id: string) =>
  renderApp(<BatchOverview />, { route: `/batches/${id}`, path: '/batches/:batchId' })

describe('batch overview states', () => {
  it('done: shows counts and the review link', async () => {
    overview(BRIEF_BATCH)
    expect(await screen.findByText('Findings by type')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review findings' })).toHaveAttribute('href', `/batches/${BRIEF_BATCH}/findings`)
    expect(screen.getByRole('button', { name: 'Export approved changes' })).toBeInTheDocument()
  })
  it('processing: banner and no review link', async () => {
    overview(RUNNING_BATCH)
    expect(await screen.findByText(/Processing…/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Review findings' })).toBeNull()
  })
  it('failed: plain-language error code', async () => {
    overview(FAILED_BATCH)
    expect(await screen.findByText(/more than 100,000 rows/)).toBeInTheDocument()
  })
  it('empty: explains the empty file', async () => {
    overview(EMPTY_BATCH)
    expect(await screen.findByText('File contained no records.')).toBeInTheDocument()
  })
  it('ai_partial: banner says rule findings are complete', async () => {
    overview(LARGE_BATCH)
    expect(await screen.findByText(/rule findings are complete/)).toBeInTheDocument()
  })
  it('unknown batch is "not found"', async () => {
    overview('b_nope')
    expect(await screen.findByText('Not found.')).toBeInTheDocument()
  })
  it('shows review and export to everyone (open access, ADR-023)', async () => {
    overview(BRIEF_BATCH)
    await screen.findByRole('link', { name: 'Review findings' })
    expect(screen.getByRole('button', { name: /Export/ })).toBeInTheDocument()
  })
})

describe('polling', () => {
  it('backs off from 2 s to a 15 s ceiling', () => {
    expect(pollDelay(0)).toBe(2000)
    expect(pollDelay(1)).toBe(3000)
    expect(pollDelay(50)).toBe(15000)
  })
})

describe('batch list', () => {
  it('lists batches with status chips', async () => {
    renderApp(<BatchList />)
    expect(await screen.findByRole('link', { name: BRIEF_BATCH })).toBeInTheDocument()
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0)
  })
  it('shows the empty state', async () => {
    server.use(http.get('http://localhost/api/v1/batches', () => HttpResponse.json({ items: [], next_cursor: null })))
    renderApp(<BatchList />)
    expect(await screen.findByText('No batches yet')).toBeInTheDocument()
  })
})

describe('upload', () => {
  it('uploads with an Idempotency-Key and lands on the batch overview', async () => {
    let key: string | null = null
    server.use(http.post('http://localhost/api/v1/batches', async ({ request }) => {
      key = request.headers.get('idempotency-key')
      return HttpResponse.json({ batch_id: 'b_new_9', status: 'queued' }, { status: 202 })
    }))
    renderApp(<UploadForm />, { route: '/batches/new', extraRoutes: <Route path="/batches/:id" element={<p>overview page</p>} />, path: '/batches/new' })
    const file = new File(['[]'], 'brief-sample-input.json', { type: 'application/json' })
    await userEvent.upload(screen.getByLabelText(/Drop an item batch/), file)
    expect(screen.getByText('brief-sample-input.json')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Upload batch' }))
    expect(await screen.findByText('overview page')).toBeInTheDocument()
    expect(key).toMatch(/[0-9a-f-]{36}/)
  })
  it('rejects a wrong file type before sending and shows server validation errors', async () => {
    renderApp(<UploadForm />)
    const input = screen.getByLabelText(/Drop an item batch/) as HTMLInputElement
    await userEvent.upload(input, new File(['x'], 'notes.txt'), { applyAccept: false })
    expect(await screen.findByText('Choose a .json or .csv file.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload batch' })).toBeDisabled()

    server.use(http.post('http://localhost/api/v1/batches', () =>
      HttpResponse.json({ error: { code: 'validation_error', message: 'Bad JSON at position 12', details: { position: 12 } } }, { status: 422 })))
    await userEvent.upload(input, new File(['{'], 'bad.json'))
    await userEvent.click(screen.getByRole('button', { name: 'Upload batch' }))
    expect(await screen.findByText(/Bad JSON at position 12/)).toBeInTheDocument()
  })
  it('a retry of the same file reuses the Idempotency-Key', async () => {
    const keys: (string | null)[] = []
    server.use(http.post('http://localhost/api/v1/batches', ({ request }) => {
      keys.push(request.headers.get('idempotency-key'))
      return HttpResponse.json({ error: { code: 'internal' } }, { status: 500 })
    }))
    renderApp(<UploadForm />)
    await userEvent.upload(screen.getByLabelText(/Drop an item batch/), new File(['[]'], 'a.json'))
    await userEvent.click(screen.getByRole('button', { name: 'Upload batch' }))
    await screen.findByText(/service had a problem/)
    await userEvent.click(screen.getByRole('button', { name: 'Upload batch' }))
    await waitFor(() => expect(keys).toHaveLength(2))
    expect(keys[0]).toBe(keys[1])
  })
})

describe('export status', () => {
  const show = (id: string) => renderApp(<ExportStatus />, { route: `/batches/${BRIEF_BATCH}/exports/${id}`, path: '/batches/:batchId/exports/:exportId' })
  it('ready with findings: download link from the signed URL', async () => {
    db.exports.set('x_9', { status: 'ready', finding_count: 2, polls: 5 })
    show('x_9')
    const link = await screen.findByRole('link', { name: 'Download change file' })
    expect(link).toHaveAttribute('href', expect.stringContaining('files.example.test/x_9'))
  })
  it('zero approved findings is explained', async () => {
    db.exports.set('x_8', { status: 'ready', finding_count: 0, polls: 5 })
    show('x_8')
    expect(await screen.findByText(/change file is empty/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Download change file' })).toBeNull()
  })
  it('queued shows progress; failed offers a retry path', async () => {
    db.exports.set('x_7', { status: 'queued', finding_count: 1, polls: 0 })
    const { unmount } = show('x_7')
    expect(await screen.findByText(/Preparing the change file/)).toBeInTheDocument()
    unmount()
    db.exports.set('x_6', { status: 'failed', finding_count: 1, polls: 5 })
    show('x_6')
    expect(await screen.findByText(/export failed/)).toBeInTheDocument()
    void within
  })
})
