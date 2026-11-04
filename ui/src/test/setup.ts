import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from '../mocks/server'
import { resetDb } from '../mocks/data'

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  server.resetHandlers()
  resetDb()
})
afterAll(() => server.close())

// jsdom does no layout; give elements a viewport so the virtualised table renders rows.
Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 800 })
Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 1000 })
