import { formatDateTime } from '../../lib/format.js'

export const supportName = (conversation) => conversation.CustomerName || 'Khách hàng ' + conversation.CustomerId.slice(0, 8)
export const supportTime = (value) => formatDateTime(value).split(' ')[0]
// Who is helping the customer: '' while the chat waits in the queue.
export const supportAgent = (conversation, user) => !conversation.AssignedStaffId ? ''
  : conversation.AssignedStaffId === user?.UserId ? 'Bạn' : conversation.AssignedStaffName || 'Nhân viên khác'
export function supportPreview(conversation) {
  const message = conversation.LastMessage
  if (!message) return 'Chưa có tin nhắn.'
  return message.Content || ({ Image: '[Hình ảnh]', Product: '[Sản phẩm]' })[message.MessageType] || 'Tin nhắn mới'
}
