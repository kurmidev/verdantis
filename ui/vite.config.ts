import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    env: { VITE_API_BASE: 'http://localhost/api/v1', VITE_USE_MOCKS: 'false' },
    coverage: { include: ['src/lib/**', 'src/hooks/**', 'src/features/**'], reporter: ['text-summary'] },
  },
})
