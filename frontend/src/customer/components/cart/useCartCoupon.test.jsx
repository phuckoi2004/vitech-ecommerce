import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import useCartCoupon from './useCartCoupon.js'

const withAccessToken = (call) => call('customer-token')
const preview = { Code: 'SALE', Subtotal: '100000', EligibleSubtotal: '100000', DiscountAmount: '10000' }
const expired = { detail: 'Mã giảm giá đã hết hạn', code: 'coupon_expired' }
const json = (body, status = 200) => new Response(JSON.stringify(body), { status,
  headers: { 'Content-Type': 'application/json' } })
const cart = (quantity = 1) => ({ Items: [{ CartItemId: 'c1', Quantity: quantity, CurrentPrice: '100000',
  IsSelected: true, IsAvailable: true }], SelectedSubtotal: String(quantity * 100000) })

function useCoupon(value) {
  return useCartCoupon({ userId: 'customer', cart: value, withAccessToken })
}

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear() })

test('checking an applied coupon again replaces its discount with the latest server verdict', async () => {
  const fetch = vi.fn(async () => json(expired, 400))
  vi.stubGlobal('fetch', fetch)
  const { result } = renderHook(() => useCoupon(cart()))
  act(() => result.current.apply(preview))
  expect(result.current.status).toBe('ok')
  expect(fetch).not.toHaveBeenCalled()

  act(() => result.current.retry())
  await waitFor(() => expect(result.current.status).toBe('invalid'))
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(result.current).toMatchObject({ code: 'SALE', preview: null, error: expired.detail })
})

test('returning to an earlier quantity checks whether the applied coupon has expired', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(json({ ...preview, Subtotal: '200000', EligibleSubtotal: '200000', DiscountAmount: '20000' }))
    .mockResolvedValueOnce(json(expired, 400))
  vi.stubGlobal('fetch', fetch)
  const { result, rerender } = renderHook(({ value }) => useCoupon(value), { initialProps: { value: cart() } })
  act(() => result.current.apply(preview))

  rerender({ value: cart(2) })
  await waitFor(() => expect(result.current.preview?.DiscountAmount).toBe('20000'))
  rerender({ value: cart(1) })
  await waitFor(() => expect(result.current.status).toBe('invalid'))
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(result.current.preview).toBeNull()
})

test('rapid quantity changes do not reuse an earlier response or restore a discount from a late response', async () => {
  sessionStorage.setItem('vietech-cart-coupon:customer', 'SALE')
  let answerChanged, answerReturned
  const changed = new Promise((resolve) => { answerChanged = resolve })
  const returned = new Promise((resolve) => { answerReturned = resolve })
  const fetch = vi.fn().mockResolvedValueOnce(json(preview)).mockReturnValueOnce(changed).mockReturnValueOnce(returned)
  vi.stubGlobal('fetch', fetch)
  const { result, rerender } = renderHook(({ value }) => useCoupon(value), { initialProps: { value: cart() } })
  await waitFor(() => expect(result.current.status).toBe('ok'))
  act(() => result.current.apply(preview))

  rerender({ value: cart(2) })
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  rerender({ value: cart(1) })
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
  expect(result.current.status).toBe('checking')
  expect(result.current.preview).toBeNull()

  await act(async () => { answerReturned(json(expired, 400)) })
  await waitFor(() => expect(result.current.status).toBe('invalid'))
  await act(async () => { answerChanged(json({ ...preview, Subtotal: '200000', DiscountAmount: '20000' })) })
  expect(result.current.status).toBe('invalid')
  expect(result.current.preview).toBeNull()
})
