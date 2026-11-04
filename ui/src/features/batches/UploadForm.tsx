import { useMutation } from '@tanstack/react-query'
import { useState, type DragEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useIdempotencyKey } from '../../hooks/useIdempotencyKey'
import { api } from '../../lib/api/client'
import { ApiError, describeError } from '../../lib/api/errors'
import './batches.css'

const ACCEPT = /\.(json|csv)$/i

export function UploadForm() {
  const nav = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [drag, setDrag] = useState(false)
  const [localError, setLocalError] = useState('')
  // Same file = same intent = same key, so a retry cannot create a second batch.
  const key = useIdempotencyKey(file ? `${file.name}:${file.size}:${file.lastModified}` : '')
  const upload = useMutation({
    mutationFn: (f: File) => api.uploadBatch(f, key),
    onSuccess: (r) => nav(`/batches/${r.batch_id}`),
  })

  const pick = (f: File | undefined) => {
    upload.reset()
    if (!f) return
    if (!ACCEPT.test(f.name)) {
      setFile(null)
      setLocalError('Choose a .json or .csv file.') // convenience check; the server validates
      return
    }
    setLocalError('')
    setFile(f)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDrag(false)
    pick(e.dataTransfer.files[0])
  }
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (file) upload.mutate(file)
  }
  const err = upload.error
  const details = err instanceof ApiError && err.details ? JSON.stringify(err.details) : ''

  return (
    <form className="upload" onSubmit={onSubmit} noValidate>
      <label
        className={`dropzone${drag ? ' is-drag' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <input type="file" accept=".json,.csv" className="visually-hidden" onChange={(e) => pick(e.target.files?.[0])} />
        <span className="dropzone-title">{file ? file.name : 'Drop an item batch here'}</span>
        <span className="dropzone-hint">{file ? `${(file.size / 1024).toFixed(1)} kB` : 'or choose a JSON or CSV file'}</span>
      </label>
      {localError && <p role="alert" className="field-error">{localError}</p>}
      {err && (
        <p role="alert" className="field-error">
          {describeError(err)} {details && <span className="mono small">{details}</span>}
        </p>
      )}
      <button type="submit" className="btn btn-primary" disabled={!file || upload.isPending}>
        {upload.isPending ? 'Uploading…' : 'Upload batch'}
      </button>
      {upload.isPending && <p role="status">Uploading and queuing {file?.name}…</p>}
    </form>
  )
}
