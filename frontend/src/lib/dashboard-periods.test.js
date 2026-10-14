import { describe, expect, test } from 'vitest'
import { browserMonth, growth, monthPeriod, recentMonths } from './dashboard-periods.js'

describe('dashboard calendar', () => {
  test('uses the computer local calendar and includes the current month', () => {
    expect(browserMonth(new Date(2026, 9, 13))).toBe('2026-10')
    expect(recentMonths('2026-10')).toEqual(['2026-06', '2026-07', '2026-08', '2026-09', '2026-10'])
  })
  test('crosses the year boundary and computes inclusive leap-year month ends', () => {
    expect(recentMonths('2027-01')).toEqual(['2026-09', '2026-10', '2026-11', '2026-12', '2027-01'])
    expect(monthPeriod('2028-02')).toEqual({ date_from: '2028-02-01', date_to: '2028-02-29' })
    expect(monthPeriod('2026-02').date_to).toBe('2026-02-28')
    expect(monthPeriod('2026-12').date_to).toBe('2026-12-31')
  })
  test('does not invent a growth rate when there is no previous revenue', () => {
    expect(growth(100, 0)).toBeNull()
    expect(growth(undefined, 100)).toBeNull()
    expect(growth(0, 100)).toBe(-100)
    expect(growth(120, 100)).toBe(20)
  })
})
