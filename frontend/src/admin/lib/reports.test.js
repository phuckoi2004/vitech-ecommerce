import { expect, test } from 'vitest'
import { defaultReportFilters, reportPeriods, reportPeriod, reportQuery, reportRate } from './reports.js'

test('browser clock chooses current month and supplies all twelve months plus recent five', () => {
  const now = new Date(2026, 9, 15)
  expect(defaultReportFilters(now).period).toBe('2026-10')
  const options = reportPeriods(now)
  expect(options).toHaveLength(13)
  expect(options[0]).toEqual(['2026-01', 'Tháng 1/2026'])
  expect(options[11]).toEqual(['2026-12', 'Tháng 12/2026'])
  expect(options[12]).toEqual(['recent', '5 tháng gần nhất'])
  expect(reportPeriod(defaultReportFilters(now), now)).toEqual({ date_from: '2026-10-01', date_to: '2026-10-31' })
  expect(reportPeriod({ period: '2024-02' }, now)).toEqual({ date_from: '2024-02-01', date_to: '2024-02-29' })
})

test('recent five includes current month, handles year boundaries and retains catalog filters', () => {
  const filter = { ...defaultReportFilters(), period: 'recent', customer_id: 'c1', supplier_id: 's1', product_id: 'p1' }
  expect(reportQuery(filter, new Date(2026, 9, 15))).toEqual({ date_from: '2026-06-01', date_to: '2026-10-31', product_id: 'p1' })
  expect(reportPeriod(filter, new Date(2026, 0, 1))).toEqual({ date_from: '2025-09-01', date_to: '2026-01-31' })
  expect(reportRate(0, 0)).toBe('0%')
  expect(reportRate(1, 3)).toBe('33,3%')
})

