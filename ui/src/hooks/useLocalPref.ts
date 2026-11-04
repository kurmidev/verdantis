import { useCallback, useState } from 'react'

/** Per-viewer convenience: must work with storage empty or blocked (LLD 13 3.4). */
export function useLocalPref(key: string, initial: boolean): [boolean, (v: boolean) => void] {
  const [value, setValue] = useState(() => {
    try {
      const v = localStorage.getItem(key)
      return v === null ? initial : v === '1'
    } catch {
      return initial
    }
  })
  const set = useCallback(
    (v: boolean) => {
      setValue(v)
      try {
        localStorage.setItem(key, v ? '1' : '0')
      } catch {
        /* storage blocked: keep in-memory value */
      }
    },
    [key],
  )
  return [value, set]
}
