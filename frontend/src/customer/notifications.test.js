import { expect, test } from 'vitest'
import { customerNotificationTarget } from './notifications.js'

const id = '11111111-1111-4111-8111-111111111111'
test('chat notifications open their exact conversation inside the customer portal', () => {
  expect(customerNotificationTarget({ ReferenceType: 'Conversation', ReferenceId: id })).toEqual({ kind: 'link', to: '/tu-van?conversation=' + id })
})
test.each(['Order', 'WarrantyRequest', 'ReturnRequest'])('validates %s references before reading a customer resource', type => {
  expect(customerNotificationTarget({ ReferenceType: type, ReferenceId: id }).kind).toBe('detail')
  expect(customerNotificationTarget({ ReferenceType: type, ReferenceId: '../admin/users' })).toBeNull()
})
test.each(['/admin', '/admin/orders/' + id, '//evil.test/path', 'https://evil.test/', '/dang-nhap', '/does-not-exist', '/%61dmin/users'])('never links a customer notification to %s', ActionUrl => {
  expect(customerNotificationTarget({ ActionUrl })).toBeNull()
})
test('keeps links to existing customer pages and product slugs', () => {
  expect(customerNotificationTarget({ ActionUrl: '/san-pham/dien-thoai' })).toEqual({ kind: 'link', to: '/san-pham/dien-thoai' })
  expect(customerNotificationTarget({ ActionUrl: '/tin-tuc/bai-viet' }).to).toBe('/tin-tuc/bai-viet')
})
