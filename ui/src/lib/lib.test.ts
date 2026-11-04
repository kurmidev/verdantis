import { describe, expect, it } from 'vitest'
import { formatValue, issueLabel, sourceLabel } from './format'
import { describeBatchError, describeError, ApiError } from './api/errors'

describe('format', () => {
  it('marks blanks explicitly and keeps raw values', () => {
    expect(formatValue('')).toBe('(blank)')
    expect(formatValue(null)).toBe('(blank)')
    expect(formatValue(' EA ')).toBe(' EA ')
    expect(formatValue({ a: 1 })).toBe('{"a":1}')
  })
  it('labels sources and falls back to raw text', () => {
    expect(sourceLabel('ai_suggestion')).toBe('AI')
    expect(sourceLabel('quantum')).toBe('quantum')
    expect(issueLabel('missing_part_number')).toBe('Missing part number')
  })
})

describe('error messages', () => {
  it('explains batch error codes and 409/413', () => {
    expect(describeBatchError('too_many_rows')).toContain('Split')
    expect(describeError(new ApiError(409, 'state_conflict', ''))).toContain('Already decided')
    expect(describeError(new ApiError(413, 'payload_too_large', ''))).toContain('too large')
  })
})
