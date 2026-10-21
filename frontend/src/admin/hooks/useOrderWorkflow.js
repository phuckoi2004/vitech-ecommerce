import { useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import useAdminQuery from './useAdminQuery.js'
import { canCancelOrder, canOperateOrder, ORDER_NEXT, orderStatusLabel, paymentStatusLabel } from '../lib/orders.js'
import { confirmCodDelivery, updateOrderStatus } from '../services/orders.js'

// Shared by the full detail page and quick actions: one set of payment, serial and status rules.
export default function useOrderWorkflow(orderId, initialAction, onDone) {
  const auth = useInternalAuth()
  const detail = useAdminQuery('/admin/orders/' + encodeURIComponent(orderId))
  const order = detail.data
  const payment = useAdminQuery('/payment-methods/' + encodeURIComponent(order?.PaymentMethodId ?? ''), {}, Boolean(order?.PaymentMethodId))
  const needsSerials = Boolean(order && ['Confirmed', 'Processing', 'Shipping', 'Delivered', 'Completed'].includes(order.OrderStatus))
  const serials = useAdminQuery('/admin/orders/' + encodeURIComponent(orderId) + '/serials', {}, needsSerials)
  const [requestedIntent, setIntent] = useState(initialAction)
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [collected, setCollected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const writing = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const canUpdate = canOperateOrder(order, auth)
  const next = order ? ORDER_NEXT[order.OrderStatus] : null
  const intent = canUpdate && (requestedIntent === 'advance' ? Boolean(next) : requestedIntent === 'cancel' && canCancelOrder(order)) ? requestedIntent : null
  const cod = payment.data?.Code === 'COD'
  const codDelivery = order?.OrderStatus === 'Shipping' && cod
  // A transfer (non-COD) order is confirmed only once paid (backend OrderService: order_not_paid); COD before collection.
  const awaitingPayment = Boolean(order?.OrderStatus === 'Pending' && payment.data && !cod && order.PaymentStatus !== 'Paid')
  const serialItems = Array.isArray(serials.data) ? serials.data : []
  let blocked = ''
  if (order?.OrderStatus === 'Pending') {
    if (payment.loading || !payment.data) blocked = 'Cần tải được phương thức thanh toán trước khi xác nhận đơn.'
    else if (awaitingPayment) {
      blocked = 'Đơn thanh toán chuyển khoản chỉ được xác nhận sau khi khách đã thanh toán (hiện tại: '
        + paymentStatusLabel(order.PaymentStatus) + ').'
    }
  } else if (order && ['Processing', 'Shipping'].includes(order.OrderStatus)) {
    if (payment.loading || !payment.data) blocked = 'Cần tải được phương thức thanh toán trước khi chuyển trạng thái.'
    else if (order.OrderStatus === 'Processing') {
      if (serials.loading || !Array.isArray(serials.data)) blocked = 'Cần tải được danh sách Serial/IMEI trước khi giao hàng.'
      else if (!cod && order.PaymentStatus !== 'Paid') blocked = 'Đơn thanh toán trực tuyến phải được thanh toán trước khi giao hàng.'
    } else if (cod && order.PaymentStatus !== 'Pending') blocked = 'Trạng thái thanh toán hiện tại không cho phép xác nhận thu tiền COD.'
  }

  async function write(call, after) {
    if (!canUpdate || writing.current) return false
    writing.current = true
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await auth.withAccessToken(call)
      window.dispatchEvent(new Event('admin-order-updated'))
      if (mounted.current) after?.(result)
      return true
    } catch (failure) {
      if (mounted.current) { setError(failure.message); detail.refresh() }
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

  function choose(action) { setIntent(action); setError(''); setNote(''); setReason(''); setCollected(false) }
  return { detail, order, payment, needsSerials, serials, intent, note, reason, collected, busy, error, notice, canUpdate, next, codDelivery, awaitingPayment, serialItems, blocked, write, submitStatus, choose, setNote, setReason, setCollected, setNotice }
}
