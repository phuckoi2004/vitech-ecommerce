import { safeNext } from '../../auth/session.js'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const REFERENCES = {
  PurchaseOrder: ['purchases:view', '/admin/purchases/'],
  WarrantyRequest: ['warranties:view', '/admin/warranties/'],
  ReturnRequest: ['returns:view', '/admin/returns/'],
}

export function notificationTarget(notification, permissions) {
  // Existing stock alerts contain a variant reference, including alerts created
  // before a navigation URL was available. Never infer the SKU from the message.
  if (notification.NotificationType === 'LowStock' && notification.ReferenceType === 'ProductVariant') {
    if (!permissions.includes('products:view')) return null
    if (typeof notification.ReferenceId === 'string' && UUID.test(notification.ReferenceId)) {
      return '/admin/products?' + new URLSearchParams({ dialog: 'view', variant: notification.ReferenceId })
    }
  }
  const reference = REFERENCES[notification.ReferenceType]
  if (reference) {
    if (!permissions.includes(reference[0])) return null
    if (typeof notification.ReferenceId === 'string' && UUID.test(notification.ReferenceId)) return reference[1] + notification.ReferenceId
    return null
  }
  if (notification.ReferenceType === 'Conversation' && !permissions.includes('chat:view')) return null
  return safeNext(notification.ActionUrl, 'admin')
}
