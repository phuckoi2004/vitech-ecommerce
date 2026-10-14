import { useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import useAdminQuery from './useAdminQuery.js'
import { canCancelOrder, ORDER_NEXT, orderStatusLabel, parseSerialNumbers } from '../lib/orders.js'
import { assignOrderSerials, confirmCodDelivery, updateOrderStatus } from '../services/orders.js'

// Shared by the full detail page and quick actions: one set of payment, serial and status rules.
export default function useOrderWorkflow(orderId, initialAction, onDone) {
  const auth = useInternalAuth()
  const detail = useAdminQuery('/admin/orders/' + encodeURIComponent(orderId))
  const order = detail.data
  const payment = useAdminQuery('/payment-methods/' + encodeURIComponent(order?.PaymentMethodId ?? ''), {}, Boolean(order?.PaymentMethodId))
  const needsSerials = Boolean(order && ['Processing', 'Shipping', 'Delivered', 'Completed'].includes(order.OrderStatus))
  const serials = useAdminQuery('/admin/orders/' + encodeURIComponent(orderId) + '/serials', {}, needsSerials)
  const [intent, setIntent] = useState(initialAction)
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [collected, setCollected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const writing = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const canUpdate = auth.permissions.includes('orders:update')
  const next = order ? ORDER_NEXT[order.OrderStatus] : null
  const cod = payment.data?.Code === 'COD'
  const codDelivery = order?.OrderStatus === 'Shipping' && cod
  const serialItems = Array.isArray(serials.data) ? serials.data : []
  let blocked = ''
  if (order && ['Processing', 'Shipping'].includes(order.OrderStatus)) {
    if (payment.loading || !payment.data) blocked = 'Cần tải được phương thức thanh toán trước khi chuyển trạng thái.'
    else if (order.OrderStatus === 'Processing') {
      if (serials.loading || !Array.isArray(serials.data)) blocked = 'Cần tải được danh sách Serial/IMEI trước khi giao hàng.'
      else if (serialItems.some((item) => item.IsSerialTracked && item.SerialNumbers.length !== item.Quantity)) blocked = 'Cần gán đủ Serial/IMEI thực tế cho các sản phẩm trước khi giao hàng.'
      else if (!cod && order.PaymentStatus !== 'Paid') blocked = 'Đơn thanh toán trực tuyến phải được thanh toán trước khi giao hàng.'
    } else if (cod && order.PaymentStatus !== 'Pending') blocked = 'Trạng thái thanh toán hiện tại không cho phép xác nhận thu tiền COD.'
  }

  async function write(call, after) {
    if (!canUpdate || writing.current) return false
    writing.current = true
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await auth.withAccessToken(call)
      if (mounted.current) after?.(result)
      return true
    } catch (failure) {
      if (mounted.current) setError(failure.message)
      return false
    } finally {
      writing.current = false
      if (mounted.current) setBusy(false)
    }
  }

  async function submitStatus(event) {
    event.preventDefault()
    if (!canUpdate || !order || writing.current) return
    if (intent === 'cancel') {
      if (!canCancelOrder(order)) return
      if (!reason.trim()) { setError('Vui lòng nhập lý do hủy đơn.'); return }
      await write((token) => updateOrderStatus(token, orderId, { OrderStatus: 'Cancelled', CancelReason: reason.trim(), Note: note.trim() || null }), () => onDone('Đã hủy đơn ' + order.OrderCode + '.'))
    } else if (intent === 'advance' && next && !blocked) {
      if (codDelivery && !collected) { setError('Cần xác nhận đã thu đủ tiền COD.'); return }
      const body = { Note: note.trim() || null }
      await write((token) => codDelivery ? confirmCodDelivery(token, orderId, body) : updateOrderStatus(token, orderId, { OrderStatus: next[0], ...body }), () => onDone('Đã cập nhật đơn ' + order.OrderCode + ': ' + orderStatusLabel(next[0]) + '.'))
    }
  }

  function assign(item, text) {
    let numbers
    try {
      numbers = parseSerialNumbers(text)
      if (numbers.length + item.SerialNumbers.length > item.Quantity) throw new Error('Số Serial/IMEI vượt quá số lượng sản phẩm của dòng đơn.')
    } catch (failure) { setError(failure.message); return false }
    return write((token) => assignOrderSerials(token, orderId, { Items: [{ OrderItemId: item.OrderItemId, SerialNumbers: numbers }] }), () => { serials.refresh(); setNotice('Đã gán Serial/IMEI.'); setCollected(false) })
  }

  function choose(action) { setIntent(action); setError(''); setNote(''); setReason(''); setCollected(false) }
  return { detail, order, payment, needsSerials, serials, intent, note, reason, collected, busy, error, notice, canUpdate, next, codDelivery, serialItems, blocked, write, submitStatus, assign, choose, setNote, setReason, setCollected, setNotice }
}
