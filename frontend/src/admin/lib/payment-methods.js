export const PAYMENT_PAGE_TITLES = { new: 'Thêm phương thức thanh toán', edit: 'Sửa phương thức thanh toán' }
export function paymentListSearch(params) {
  const next = new URLSearchParams(params)
  next.delete('dialog'); next.delete('method')
  return next.size ? '?' + next.toString() : ''
}
export function paymentPagePath(mode, id, params) {
  return '/admin/payments' + (mode === 'new' ? '/new' : '/' + encodeURIComponent(id) + '/edit') + paymentListSearch(params)
}
export function paymentValidation(body, creating) {
  if (!body.Name || (creating && !body.Code) || !Number.isInteger(body.DisplayOrder) || body.DisplayOrder < -2147483648 || body.DisplayOrder > 2147483647) return 'Vui lòng nhập mã, tên phương thức và thứ tự hiển thị là số nguyên hợp lệ.'
  return ''
}
