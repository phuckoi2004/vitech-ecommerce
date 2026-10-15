import { expect, test } from 'vitest'
import { notificationTarget } from './notifications.js'

test('stock references override a stale URL without relying on notification content', () => {
  const id = 'ABCDEF12-1234-4567-89AB-123456789ABC'
  expect(notificationTarget({ NotificationType: 'LowStock', ReferenceType: 'ProductVariant', ReferenceId: id, Content: 'Mã khác không dùng để điều hướng', ActionUrl: '/admin/inventory' }, ['products:view'])).toBe('/admin/products?dialog=view&variant=' + id)
})

test.each(['', '../users', 'id&dialog=delete', '<script>', null])('malformed stock reference %s never fabricates a product URL', (id) => {
  expect(notificationTarget({ NotificationType: 'LowStock', ReferenceType: 'ProductVariant', ReferenceId: id }, ['products:view'])).toBeNull()
})

test('other notification links retain existing internal navigation and reject external targets', () => {
  expect(notificationTarget({ ActionUrl: '/admin/orders/123?source=notification' }, [])).toBe('/admin/orders/123?source=notification')
  for (const ActionUrl of ['https://example.com', '//example.com', '/admin/login', '/san-pham', 'javascript:alert(1)']) expect(notificationTarget({ ActionUrl }, [])).toBeNull()
})
