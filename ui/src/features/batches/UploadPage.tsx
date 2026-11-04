import { UploadForm } from './UploadForm'

export default function UploadPage() {
  return (
    <section aria-labelledby="h-upload">
      <h1 id="h-upload" className="page-title">Upload a batch</h1>
      <p className="lede">Item records only; nothing here changes your item data. Findings come back for review.</p>
      <UploadForm />
    </section>
  )
}
