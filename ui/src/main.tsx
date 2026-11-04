import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/newsreader/latin-500.css'
import './styles/tokens.css'
import './styles/global.css'
import { App } from './app/App'

async function start() {
  // Literal comparison so the mock layer is dropped from production builds.
  if (import.meta.env.VITE_USE_MOCKS === 'true') {
    const { worker } = await import('./mocks/browser')
    await worker.start({ onUnhandledFrame: 'bypass' })
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
void start()
