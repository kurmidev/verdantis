const env = import.meta.env

export const config = {
  apiBase: (env.VITE_API_BASE as string | undefined) ?? '/api/v1',
  useMocks: env.VITE_USE_MOCKS === 'true',
}
