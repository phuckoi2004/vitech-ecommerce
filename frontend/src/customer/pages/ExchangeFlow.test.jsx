import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import CustomerLayout from '../layouts/CustomerLayout.jsx'
import CatalogPage from './CatalogPage.jsx'
import CheckoutPage from './CheckoutPage.jsx'
import ProductPage from './ProductPage.jsx'

const context = { ReturnRequestId: 'r1', RequestCode: 'DT-01', Status: 'Approved', CategoryId: 'phone',
  OriginalProductId: 'p1', OriginalVariantId: 'v1', CreditLimit: '100000', OriginalInStock: false,
  CanChoose: true, Committed: false, OrderId: null }
const product = { ProductId: 'p2', CategoryId: 'phone', Name: 'Máy đổi', Slug: 'may-doi', Images: [], Specifications: {},
  Variants: [{ ProductVariantId: 'v2', VariantName: '256GB Đen', Color: 'Đen', IsActive: true, StockQuantity: 3,
    Price: '120000', SalePrice: '90000', OriginalPrice: '120000', DiscountAmount: '30000' }] }
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function mount(url, { exchange = context, products = [product], placed } = {}) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async (input, init = {}) => {
    const address = new URL(input, 'http://localhost')
    const path = address.pathname.replace(/^\/api/, '')
    calls.push({ path, query: Object.fromEntries(address.searchParams), method: init.method || 'GET', body: init.body && JSON.parse(init.body) })
    if (path === '/return-requests/r1/exchange') return json(exchange)
    if (path === '/return-requests/r1/exchange-order') return json(placed || { OrderId: 'new-order', TotalAmount: '0', PaymentStatus: 'Paid' })
    if (path === '/products/filters') return json({ Categories: [{ CategoryId: 'phone', Name: 'Điện thoại' }, { CategoryId: 'other', Name: 'Laptop' }] })
    if (path === '/products') return json({ Items: products, Total: products.length, Page: 1, PageSize: 20 })
    if (['/products/p2', '/products/slug/may-doi'].includes(path)) return json(product)
    if (path === '/products/p1') return json({ ...product, ProductId: 'p1', Variants: [{ ...product.Variants[0], ProductVariantId: 'v1' }] })
    if (path === '/products/p2/reviews') return json({ Items: [], Total: 0, Page: 1, PageSize: 10 })
    return json({ detail: 'Không có dữ liệu' }, 404)
  }))
  const router = createMemoryRouter([{ element: <CustomerLayout />, children: [
    { path: '/tim-kiem', element: <CatalogPage /> },
    { path: '/san-pham/:slug', element: <ProductPage /> },
    { path: '/dat-hang', element: <CheckoutPage /> },
    { path: '/don-hang/:orderId', element: <p>Trang đơn hàng mới</p> },
    { path: '/', element: <p>Trang chủ bình thường</p> },
    { path: '/tai-khoan', element: <p>Phiếu đổi trả</p> },
  ] }], { initialEntries: [url] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Customer' })}><RouterProvider router={router} /></AuthContext.Provider>)
  return { router, calls }
}
afterEach(() => vi.unstubAllGlobals())

test('exchange search locks the category from the server, keeps context through product and checkout, and never adds to cart', async () => {
  const { calls, router } = mount('/tim-kiem?exchange=r1&category=other&q=outside')
  await screen.findByRole('heading', { name: 'Máy đổi' })
  expect(screen.getByRole('textbox', { name: 'Tìm kiếm' })).toBeDisabled()
  expect(screen.queryByRole('group', { name: 'Danh mục' })).not.toBeInTheDocument()
  const query = calls.find((call) => call.path === '/products').query
  expect(query.category_id).toBe('phone')
  expect(query.keyword).toBeUndefined()
  expect(query.in_stock).toBe('true')
  await userEvent.click(screen.getByRole('link', { name: /Máy đổi/ }))
  await screen.findByRole('button', { name: 'CHỌN MÁY ĐỔI' })
  expect(router.state.location.search).toBe('?exchange=r1')
  expect(screen.queryByRole('button', { name: 'Thêm vào giỏ hàng' })).not.toBeInTheDocument()
  expect(screen.getByRole('spinbutton', { name: 'Số lượng' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'CHỌN MÁY ĐỔI' }))
  await screen.findByRole('heading', { name: 'Xác nhận đơn đổi trả' })
  expect(router.state.location.search).toContain('variant=v2')
  expect(calls.some((call) => call.path === '/cart/items' && call.method === 'POST')).toBe(false)
})

test('zero-due exchange posts only the selected variant and navigates to a real new order', async () => {
  const { calls, router } = mount('/dat-hang?exchange=r1&variant=v2&product=p2')
  await userEvent.click(await screen.findByRole('button', { name: 'Xác nhận đổi · 0đ' }))
  await screen.findByText('Trang đơn hàng mới')
  expect(router.state.location.pathname).toBe('/don-hang/new-order')
  const request = calls.find((call) => call.path.endsWith('/exchange-order'))
  expect(request.body).toEqual({ ProductVariantId: 'v2' })
  expect(calls.some((call) => ['/orders', '/cart', '/cart/items'].includes(call.path) && call.method !== 'GET')).toBe(false)
})

test('original in stock already has an automatic order and needs no customer checkout', async () => {
  const { calls } = mount('/tim-kiem?exchange=r1', { exchange: { ...context, OriginalInStock: true,
    CanChoose: false, Committed: true, OrderId: 'automatic', OrderCode: 'VT-AUTO' } })
  await screen.findByRole('heading', { name: 'Đơn đổi trả đã tạo' })
  expect(calls.some((call) => call.path === '/products')).toBe(false)
  expect(screen.getByRole('link', { name: 'Tiếp tục đơn VT-AUTO' })).toHaveAttribute('href', '/don-hang/automatic')
  expect(screen.queryByRole('link', { name: 'Tiếp tục xác nhận đổi' })).not.toBeInTheDocument()
  expect(calls.some((call) => call.method === 'POST')).toBe(false)
})

test('pending QR resumes the existing exchange order instead of allowing another purchase', async () => {
  const { calls } = mount('/tim-kiem?exchange=r1', { exchange: { ...context, CanChoose: false, OrderId: 'pending', OrderCode: 'VT-PENDING' } })
  expect(await screen.findByRole('link', { name: 'Tiếp tục đơn VT-PENDING' })).toHaveAttribute('href', '/don-hang/pending')
  expect(calls.some((call) => call.path === '/products')).toBe(false)
})

test('an empty category asks the customer to wait and offers no other category', async () => {
  mount('/tim-kiem?exchange=r1', { products: [] })
  await screen.findByText('Danh mục chưa có sản phẩm để đổi')
  expect(screen.getByText(/Bạn cần chờ hàng trong cùng danh mục/)).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Xem tất cả sản phẩm' })).not.toBeInTheDocument()
})

test('the logo exits exchange browsing and restores the normal search', async () => {
  const { router } = mount('/tim-kiem?exchange=r1', { products: [] })
  await screen.findByText('Danh mục chưa có sản phẩm để đổi')
  await userEvent.click(screen.getByRole('link', { name: 'VieTech – Trang chủ' }))
  await waitFor(() => expect(router.state.location.search).toBe(''))
  expect(screen.getByRole('searchbox', { name: 'Tìm kiếm sản phẩm' })).toBeEnabled()
})
