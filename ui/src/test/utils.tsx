import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '../components/ui/Toast'

interface Opts {
  route?: string
  path?: string
  extraRoutes?: ReactElement
}

export function renderApp(ui: ReactElement, { route = '/', path = '*', extraRoutes }: Opts = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={[route]}>
            <Routes>
              <Route path={path} element={ui} />
              {extraRoutes}
            </Routes>
          </MemoryRouter>
        </ToastProvider>
    </QueryClientProvider>,
  )
  return { ...utils, client }
}
