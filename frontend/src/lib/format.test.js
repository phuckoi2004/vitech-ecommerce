import { describe, expect, test } from 'vitest'
import { formatCompactCount, formatDate, formatDateTime, formatMoney, formatRating } from './format.js'

describe('formatCompactCount and formatRating', () => {
  test.each([
    [0, '0'], [950, '950'], [1000, '1k'], [1250, '1,2k'], [1299, '1,2k'], [999_999, '999,9k'], [2_500_000, '2,5tr'],
    [null, '0'], ['abc', '0'],
  ])('%s → %s', (value, expected) => {
    expect(formatCompactCount(value)).toBe(expected)
  })

  test('ratings keep one decimal with a comma', () => {
    expect(formatRating('4.80')).toBe('4,8')
    expect(formatRating(5)).toBe('5,0')
    expect(formatRating('x')).toBe('')
  })
})

describe('formatMoney', () => {
  test.each([
    ['15000000.00', '15.000.000 ₫'],
    [15000000, '15.000.000 ₫'],
    ['0.00', '0 ₫'],
    ['499000', '499.000 ₫'],
  ])('%s → %s', (value, expected) => {
    expect(formatMoney(value)).toBe(expected)
  })

  test.each([[null], [undefined], [''], ['abc']])('%s has no amount', (value) => {
    expect(formatMoney(value)).toBe('—')
    expect(formatMoney(value, { fallback: '' })).toBe('')
  })
})

describe('formatDate and formatDateTime', () => {
  test('timestamps are shown in Vietnam time (UTC+7), across midnight', () => {
    expect(formatDate('2026-10-12T17:30:00Z')).toBe('13/10/2026')
    expect(formatDateTime('2026-10-12T17:30:00Z')).toBe('00:30 13/10/2026')
    expect(formatDateTime('2026-10-12T08:05:00+00:00')).toBe('15:05 12/10/2026')
    expect(formatDateTime(new Date(Date.UTC(2026, 0, 1, 0, 0)))).toBe('07:00 01/01/2026')
  })

  test('a date-only value keeps its calendar day', () => {
    expect(formatDate('2004-05-17')).toBe('17/05/2004')
  })

  test.each([[null], [''], ['not a date']])('%s has no date', (value) => {
    expect(formatDate(value)).toBe('—')
    expect(formatDateTime(value)).toBe('—')
  })
})
