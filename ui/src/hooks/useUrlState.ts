import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/** Shareable list state in the URL (LLD 13 3.4); empty string means unset. */
export function useUrlState<K extends string>(keys: readonly K[]) {
  const [sp, setSp] = useSearchParams()
  const values = Object.fromEntries(keys.map((k) => [k, sp.get(k) ?? ''])) as Record<K, string>
  const set = useCallback(
    (patch: Partial<Record<K, string>>, opts?: { replace?: boolean }) =>
      setSp(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch) as [string, string | undefined][]) {
            if (v) next.set(k, v)
            else next.delete(k)
          }
          return next
        },
        { replace: opts?.replace ?? false },
      ),
    [setSp],
  )
  return [values, set] as const
}
