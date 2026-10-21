import { expect, test } from 'vitest'
import { defaultReportFilters, reportFilters, reportPeriod, reportQuery, reportRate } from './reports.js'
const now = new Date('2026-10-21T05:00:00Z')
test('current month is month-to-date; completed and leap months remain complete', () => {
  expect(reportPeriod(defaultReportFilters(now), now)).toEqual({ date_from: '2026-10-01', date_to: '2026-10-21' })
  expect(reportPeriod({ period: 'month', month: '2024-02' }, now)).toEqual({ date_from: '2024-02-01', date_to: '2024-02-29' })
  expect(reportPeriod({ period: '2026-09' }, now)).toEqual({ date_from: '2026-09-01', date_to: '2026-09-30' })
})
test('quarters, previous years and six months cross calendar years correctly', () => {
  expect(reportPeriod({ period: 'quarter', quarter: '2', year: '2025' }, now)).toEqual({ date_from: '2025-04-01', date_to: '2025-06-30' })
  expect(reportPeriod({ period: 'year', year: '2024' }, now)).toEqual({ date_from: '2024-01-01', date_to: '2024-12-31' })
  expect(reportPeriod({ period: 'year', year: '2026' }, now).date_to).toBe('2026-10-21')
  expect(reportPeriod({ period: 'recent' }, new Date('2026-01-01T05:00:00Z'))).toEqual({ date_from: '2025-08-01', date_to: '2026-01-01' })
})
test('invalid dates, reversed and oversized ranges are rejected before querying', () => {
  for (const [from, to] of [['2026-02-30','2026-03-01'], ['2026-10-21','2026-10-01'], ['2024-01-01','2025-01-01']]) {
    expect(() => reportPeriod({ period: 'custom', date_from: from, date_to: to }, now)).toThrow()
  }
})
test('deep links preserve filters but exclude unsupported query fields', () => {
  const filter = reportFilters(new URLSearchParams('period=2025-12&brand_id=b1&sort=profit_asc'), now)
  expect(filter.month).toBe('2025-12')
  expect(filter.sort).toBe('profit_asc')
  expect(reportQuery({ ...filter, supplier_id: 'ignored' }, now)).toEqual({ date_from: '2025-12-01', date_to: '2025-12-31', brand_id: 'b1' })
  expect(reportRate(0, 0)).toBe('0%')
  expect(reportRate(1, 3)).toBe('33,3%')
})

