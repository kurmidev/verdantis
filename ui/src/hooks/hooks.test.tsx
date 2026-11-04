import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { useIdempotencyKey } from './useIdempotencyKey'
import { useLocalPref } from './useLocalPref'
import { useUrlState } from './useUrlState'

const wrap = (url: string) => ({ children }: { children: ReactNode }) => <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>

describe('useUrlState', () => {
  it('reads values and patches the URL, removing empty values', () => {
    const { result } = renderHook(() => useUrlState(['severity', 'source'] as const), { wrapper: wrap('/?severity=high') })
    expect(result.current[0]).toEqual({ severity: 'high', source: '' })
    act(() => result.current[1]({ source: 'heuristic', severity: '' }))
    expect(result.current[0]).toEqual({ severity: '', source: 'heuristic' })
  })
})

describe('useIdempotencyKey', () => {
  it('is stable for the same intent and changes when the request changes', () => {
    const { result, rerender } = renderHook(({ sig }) => useIdempotencyKey(sig), { initialProps: { sig: 'a' } })
    const first = result.current
    rerender({ sig: 'a' })
    expect(result.current).toBe(first)
    rerender({ sig: 'b' })
    expect(result.current).not.toBe(first)
  })
})

describe('useLocalPref', () => {
  it('persists and survives blocked storage', () => {
    const { result } = renderHook(() => useLocalPref('k', false))
    act(() => result.current[1](true))
    expect(localStorage.getItem('k')).toBe('1')
    const orig = Storage.prototype.getItem
    Storage.prototype.getItem = () => { throw new Error('blocked') }
    const blocked = renderHook(() => useLocalPref('k2', true))
    expect(blocked.result.current[0]).toBe(true)
    Storage.prototype.getItem = orig
  })
})
