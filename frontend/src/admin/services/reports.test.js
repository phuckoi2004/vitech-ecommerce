import { expect, test } from 'vitest'
import { formatReport } from './reports.js'

test('daily chart points and unknown cost stay intact instead of collapsing into one monthly bar', () => {
  const data = { Summary: { Revenue: '0.30', Cost: null, Profit: null }, Chart: [
    { Label: '01/10', Revenue: '0.10', Profit: null }, { Label: '02/10', Revenue: '0.20', Profit: '0.05' },
  ], Items: [{ ProductId: 'p1', Revenue: '0.30', Cost: null }] }
  const formatted = formatReport(data, 'revenue')
  expect(formatted.Chart).toEqual(data.Chart)
  expect(formatted.Summary).toEqual(data.Summary)
  expect(formatted.Items).toEqual(data.Items)
})
test('order table labels describe the placement month with the correct cancellation denominator', () => {
  const data = { Chart: [], Items: [{ DateFrom: '2026-10-01', TotalOrders: 3, CancelledOrders: 1 }] }
  const formatted = formatReport(data, 'orders')
  expect(formatted.Items[0]).toMatchObject({ PeriodLabel: 'Tháng 10/2026', CancelRate: '33,3%' })
  expect(data.Items[0].PeriodLabel).toBeUndefined()
})
