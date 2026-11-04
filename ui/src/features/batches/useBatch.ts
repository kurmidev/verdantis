import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type { Batch } from '../../lib/api/schemas'

const POLL_MIN_MS = 2000
const POLL_MAX_MS = 15000

/** Exponential backoff 2 s to 15 s (LLD 13 3.12). */
export const pollDelay = (n: number): number => Math.min(POLL_MIN_MS * 1.5 ** n, POLL_MAX_MS)

export const isSettled = (b: Pick<Batch, 'status' | 'ai_status'>): boolean =>
  b.status !== 'queued' && b.status !== 'processing' && b.ai_status !== 'running'

// Polling pauses in hidden tabs (TanStack default) and stops at a terminal state.
export function useBatch(id: string) {
  return useQuery({
    queryKey: ['batch', id],
    queryFn: ({ signal }) => api.getBatch(id, signal),
    refetchInterval: (q) => (q.state.data && !isSettled(q.state.data) ? pollDelay(q.state.dataUpdateCount) : false),
  })
}
