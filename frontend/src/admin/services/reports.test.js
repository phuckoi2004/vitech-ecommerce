import { expect, test } from 'vitest'
import { formatReport } from './reports.js'

test('one monthly bar uses exact period totals instead of weekly peak or current prices', () => {
  const data = { Period: { DateFrom: '2026-10-01', DateTo: '2026-10-31' },
    Summary: { Revenue: '0.30', PeakRevenue: '0.20', TotalOrders: 3, DeliveredOrders: 2, CancelledOrders: 1 },
    Chart: [{ DateFrom: '2026-10-01', Revenue: '0.10', TotalOrders: 1 }, { DateFrom: '2026-10-08', Revenue: '0.20', TotalOrders: 2 }],
    Items: [{ DateFrom: '2026-10-01', DateTo: '2026-10-31', TotalOrders: 3, CancelledOrders: 1 }] }
  for (const tab of ['revenue', 'orders']) {
    const formatted = formatReport(data, tab)
    expect(formatted.Chart).toHaveLength(1)
    expect(formatted.Chart[0]).toMatchObject({ Label: 'Tháng 10/2026', Revenue: '0.30', TotalOrders: 3 })
    expect(formatted.Summary.PeakRevenue).toBe('0.30')
    expect(formatted.Items[0].PeriodLabel).toBe('Tháng 10/2026')
  }
  expect(data.Summary.PeakRevenue).toBe('0.20')
})

test('five-month response keeps all five calendar points, exact revenue and empty months', () => {
  const data = { Period: { DateFrom: '2025-09-01', DateTo: '2026-01-31' },
    Summary: { Revenue: '0.30', PeakRevenue: '0.20', TotalOrders: 3 },
    Chart: ['2025-09', '2025-10', '2025-11', '2025-12', '2026-01'].map((month, i) => ({ DateFrom: month + '-01', Revenue: i === 1 ? '0.20' : i === 4 ? '0.10' : '0.00', TotalOrders: i === 1 ? 2 : i === 4 ? 1 : 0 })), Items: [] }
  const formatted = formatReport(data, 'revenue')
  expect(formatted.Chart).toHaveLength(5)
  expect(formatted.Chart.map((point) => point.Label)).toEqual(['Tháng 9/2025', 'Tháng 10/2025', 'Tháng 11/2025', 'Tháng 12/2025', 'Tháng 1/2026'])
  expect(formatted.Chart[1].Revenue).toBe('0.20')
  expect(formatted.Summary).toEqual(data.Summary)
  expect(formatted.Items).toEqual([])
})
