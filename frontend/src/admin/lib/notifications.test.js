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

test.each([
  ['Order', 'orders:view', 'orders'],
  ['PurchaseOrder', 'purchases:view', 'purchases'],
  ['WarrantyRequest', 'warranties:view', 'warranties'],
  ['ReturnRequest', 'returns:view', 'returns'],
])('%s reference opens its own detail only with the matching view permission', (ReferenceType, permission, path) => {
  const ReferenceId = '11111111-1111-4111-8111-111111111111'
  const note = { ReferenceType, ReferenceId, ActionUrl: '/admin/users' }
  expect(notificationTarget(note, [permission])).toBe('/admin/' + path + '/' + ReferenceId)
  expect(notificationTarget(note, [])).toBeNull()
  expect(notificationTarget({ ...note, ReferenceId: '../users' }, [permission])).toBeNull()
})

test('chat links require chat view access, including resolved queue alerts', () => {
  const note = { NotificationType: 'Chat', ReferenceType: 'Conversation', ActionUrl: '/admin/support' }
  expect(notificationTarget(note, [])).toBeNull()
  expect(notificationTarget(note, ['chat:view'])).toBe('/admin/support')
})
