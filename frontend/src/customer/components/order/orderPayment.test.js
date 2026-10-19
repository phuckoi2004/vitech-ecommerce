// @vitest-environment node
import { describe, expect, test } from 'vitest'
import { ApiError, errorFromResponse } from '../../../services/api/client.js'
import { awaitingTransfer, paymentStatusText, qrProblem, timeLeft } from './orderPayment.js'

describe('order payment rules', () => {
  test('"Đã thanh toán" only for a Paid order; a pending one reads by its method', () => {
    expect(paymentStatusText({ PaymentStatus: 'Paid' }, false)).toBe('Đã thanh toán')
    expect(paymentStatusText({ PaymentStatus: 'Pending' }, false)).toBe('Chờ thanh toán')
    expect(paymentStatusText({ PaymentStatus: 'Pending' }, true)).toBe('Thanh toán khi nhận hàng')
    expect(paymentStatusText({ PaymentStatus: 'Cancelled' }, false)).toBe('Đã huỷ thanh toán')
    // Cancelled once paid: the money is recorded (to give back), never said to be refunded.
    expect(paymentStatusText({ OrderStatus: 'Cancelled', PaymentStatus: 'Paid' }, false)).toBe('Đã ghi nhận thanh toán')
    expect(paymentStatusText({ OrderStatus: 'Pending', PaymentStatus: 'Paid' }, false)).toBe('Đã thanh toán')
  })

  test('a QR is given while the backend accepts one (not cancelled, shipped or paid)', () => {
    expect(awaitingTransfer({ OrderStatus: 'Pending', PaymentStatus: 'Pending' })).toBe(true)
    expect(awaitingTransfer({ OrderStatus: 'Confirmed', PaymentStatus: 'Failed' })).toBe(true)
    expect(awaitingTransfer({ OrderStatus: 'Pending', PaymentStatus: 'Paid' })).toBe(false)
    expect(awaitingTransfer({ OrderStatus: 'Cancelled', PaymentStatus: 'Cancelled' })).toBe(false)
    expect(awaitingTransfer({ OrderStatus: 'Shipping', PaymentStatus: 'Pending' })).toBe(false)
  })

  test('the countdown shows minutes:seconds and stops at 00:00', () => {
    const deadline = Date.parse('2026-10-16T03:15:00Z')
    expect(timeLeft(deadline, Date.parse('2026-10-16T03:00:00Z'))).toBe('15:00')
    expect(timeLeft(deadline, Date.parse('2026-10-16T03:14:58.200Z'))).toBe('00:02')
    expect(timeLeft(deadline, deadline + 5000)).toBe('00:00')
  })
})

describe('QR request errors', () => {
  const answer = (status, code) => errorFromResponse(status, { detail: `chi tiết ${code}`, code })

  test.each([
    [400, 'order_payment_expired', { expired: true, retry: false, refresh: false }],
    [400, 'order_not_payable', { refresh: true, retry: false }],
    [400, 'payment_request_cancelled', { refresh: true, retry: false }],
    [400, 'payment_method_is_cod', { refresh: true, retry: false }],
    [400, 'order_total_zero', { retry: false, refresh: false }],
    [400, 'qr_amount_not_supported', { retry: false, refresh: false }],
    [404, 'order_not_found', { retry: false, refresh: false }],
    [400, 'payment_gateway_not_configured', { retry: true }],
    [409, 'qr_payment_in_progress', { retry: true }],
    [502, 'qr_payment_unavailable', { retry: true }],
    [502, 'payment_code_collision', { retry: true }],
  ])('%i %s', (status, code, expected) => {
    const problem = qrProblem(answer(status, code))
    expect(problem).toMatchObject(expected)
    expect(problem.message).not.toContain('chi tiết')
  })

  test('network, server and unknown errors can be retried: asking again returns the same pending QR', () => {
    for (const failure of [new ApiError('Không kết nối được máy chủ.'), answer(500, null), answer(400, 'something_new'), new TypeError('x'), undefined]) {
      expect(qrProblem(failure)).toEqual({ retry: true, refresh: false, expired: false, message: 'Chưa lấy được mã QR thanh toán. Vui lòng thử lại.' })
    }
  })
})
