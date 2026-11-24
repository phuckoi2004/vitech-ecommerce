// Display labels stay separate from API data so editing a method preserves its stored name.
export function paymentMethodLabel(method) {
  if (method?.Name?.trim().toLowerCase() === 'sepay' || method?.Code?.trim().toUpperCase() === 'SEPAY') {
    return 'Chuyển khoản qua QR'
  }
  return method?.Name
}
