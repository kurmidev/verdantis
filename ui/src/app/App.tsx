import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { Skeleton } from '../components/ui/States'
import { ToastProvider } from '../components/ui/Toast'
import { ApiError } from '../lib/api/errors'

const BatchList = lazy(() => import('../features/batches/BatchList'))
const BatchOverview = lazy(() => import('../features/batches/BatchOverview'))
const UploadPage = lazy(() => import('../features/batches/UploadPage'))
const FindingsPage = lazy(() => import('../features/findings/FindingsPage'))
const ExportStatus = lazy(() => import('../features/exports/ExportStatus'))

const RETRIES = 3 // GETs: 3 retries, backoff with jitter (LLD 13 3.18)
const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: (n, e) => n < RETRIES && (!(e instanceof ApiError) || e.status === 0 || e.status >= 500),
      retryDelay: (n) => 1000 * 2 ** n + Math.random() * 250,
    },
    mutations: { retry: false }, // POSTs are retried by the user, reusing the same key
  },
})

function Shell() {
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="masthead">
        <p className="brand">Data-Quality <em>Assistant</em></p>
        <nav aria-label="Main navigation">
          <NavLink to="/batches" end>Batches</NavLink>
          <NavLink to="/batches/new">Upload</NavLink>
        </nav>
      </header>
      <main id="main">
        <Suspense fallback={<Skeleton label="Loading page" />}><Outlet /></Suspense>
      </main>
      <footer className="site-foot small">Open access: no sign-in required.</footer>
    </>
  )
}

export function App() {
  return (
    <QueryClientProvider client={client}>
        <ToastProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Shell />}>
                <Route index element={<Navigate to="/batches" replace />} />
                <Route path="/batches" element={<BatchList />} />
                <Route path="/batches/new" element={<UploadPage />} />
                <Route path="/batches/:batchId" element={<BatchOverview />} />
                <Route path="/batches/:batchId/findings" element={<FindingsPage />} />
                <Route path="/batches/:batchId/exports/:exportId" element={<ExportStatus />} />
                <Route path="*" element={<section className="state-block"><h1 className="page-title">Not found</h1></section>} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ToastProvider>
    </QueryClientProvider>
  )
}
