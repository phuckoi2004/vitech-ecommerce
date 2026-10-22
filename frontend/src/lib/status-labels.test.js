import { expect, test } from 'vitest'
import { formatStatus } from './status-labels.js'
import { orderStatusLabel, paymentStatusLabel } from '../admin/lib/orders.js'
import { returnStatusLabel } from '../admin/lib/returns.js'
import { warrantyHistoryLabel } from '../admin/lib/warranties.js'
import { notificationStatus } from '../customer/notifications.js'

test('status labels preserve the business meaning of each workflow in Vietnamese', () => {
  expect(orderStatusLabel('Completed')).toBe('Hoàn tất')
  expect(returnStatusLabel('Completed')).toBe('Hoàn tất')
  expect(warrantyHistoryLabel('Completed')).toBe('Đã trả khách')
  expect(paymentStatusLabel('Pending')).toBe('Chưa thanh toán')
  expect(notificationStatus('Success')).toBe('Thành công')
  expect(formatStatus('Approved', { Approved: 'Đã tiếp nhận' })).toBe('Đã tiếp nhận')
})

test('missing and unfamiliar status codes have readable fallbacks on both portals', () => {
  for (const label of [formatStatus, orderStatusLabel, paymentStatusLabel, returnStatusLabel, warrantyHistoryLabel, notificationStatus]) {
    expect(label('FutureStatus')).toBe('Chưa xác định')
    expect(label(null)).toBe('—')
    expect(label('')).toBe('—')
  }
  expect(formatStatus('constructor')).toBe('Chưa xác định')
})
