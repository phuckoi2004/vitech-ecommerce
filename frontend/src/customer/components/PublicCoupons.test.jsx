import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import PublicCoupons from './PublicCoupons.jsx'

const { request, send, session } = vi.hoisted(() => ({ request: vi.fn(), send: vi.fn(), session: { user: null } }))
vi.mock('../../services/api/client.js', () => ({ request }))
vi.mock('../../hooks/useCustomerRequest.js', () => ({ default: () => send }))
vi.mock('../../hooks/useCustomerSession.js', () => ({ default: () => session }))

const coupon = { CouponId: 'c1', Code: 'TEST300K', Name: 'Ưu đãi thử nghiệm', DiscountType: 'FixedAmount',
  DiscountValue: '300000', MinOrderValue: '20000000', MaxDiscountAmount: null, RemainingUses: 100,
  EndDate: '2026-12-01T00:00:00Z' }
const variant = { ProductVariantId: 'v1', Price: '35000000', SalePrice: '33000000', StockQuantity: 3, IsActive: true }
const quote = { CouponCode: 'TEST300K', CouponDiscount: '300000', Total: '32700000', PreviewOnly: true }

beforeEach(() => {
  request.mockReset(); send.mockReset(); session.user = null
  request.mockImplementation(async (path) => path === '/coupons' ? [coupon] : quote)
})

test('guest previews coupon without cart, login or consuming a redemption', async () => {
  render(<MemoryRouter><PublicCoupons productId="p1" variant={variant} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Xem thử giá sau mã' }))
  expect(await screen.findByText(/32\.700\.000/)).toBeInTheDocument()
  expect(screen.getByText('Còn 100 lượt sử dụng')).toBeInTheDocument()
  expect(request).toHaveBeenCalledWith('/pricing/quote', expect.objectContaining({ method: 'POST', body: {
    Items: [{ ProductVariantId: 'v1', Quantity: 1 }], CouponCode: 'TEST300K',
  } }))
  expect(send).not.toHaveBeenCalled()
  expect(request.mock.calls.some(([path]) => /cart|orders|payments/.test(path))).toBe(false)
})

test('signed-in preview uses authenticated request and displays server eligibility errors', async () => {
  session.user = { UserId: 'customer' }
  send.mockRejectedValue(new Error('Bạn đã sử dụng mã này'))
  render(<MemoryRouter><PublicCoupons productId="p1" variant={variant} compact /></MemoryRouter>)
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Xem thử giá sau mã' }))
  expect(await screen.findByText('Bạn đã sử dụng mã này')).toBeInTheDocument()
  expect(screen.queryByText(/Tiền hàng cho 1 sản phẩm/)).not.toBeInTheDocument()
})

test('empty offers stay empty and unavailable variants cannot preview', async () => {
  request.mockResolvedValue([])
  render(<MemoryRouter><PublicCoupons productId="p1" variant={{ ...variant, StockQuantity: 0 }} /></MemoryRouter>)
  expect(await screen.findByText(/Hiện chưa có mã ưu đãi/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Xem thử giá sau mã' })).not.toBeInTheDocument()
})
