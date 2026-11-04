import { useMemo, useRef } from 'react'
import { newKey } from '../lib/api/client'

/**
 * One key per intent (LLD 13 3.5, 3.18): a retry of the same intent reuses it,
 * a changed request (different signature) gets a new one.
 */
export function useIdempotencyKey(signature: string): string {
  // eslint-disable-next-line react-hooks/exhaustive-deps -- the key follows the signature only
  return useMemo(() => newKey(), [signature])
}

/** Keys for several intents on one screen: same signature reuses its key (safe retry). */
export function useIntentKeys(): (signature: string) => string {
  const keys = useRef(new Map<string, string>())
  return (signature) => {
    let k = keys.current.get(signature)
    if (!k) {
      k = newKey()
      keys.current.set(signature, k)
    }
    return k
  }
}
