import { safeNext } from '../../auth/session.js'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function notificationTarget(notification, permissions) {
  // Existing stock alerts contain a variant reference, including alerts created
  // before a navigation URL was available. Never infer the SKU from the message.
  if (notification.NotificationType === 'LowStock' && notification.ReferenceType === 'ProductVariant') {
    if (!permissions.includes('products:view')) return null
    if (typeof notification.ReferenceId === 'string' && UUID.test(notification.ReferenceId)) {
      return '/admin/products?' + new URLSearchParams({ dialog: 'view', variant: notification.ReferenceId })
    }
  }
  return safeNext(notification.ActionUrl, 'admin')
}
