import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { appRoutes } from '../../routes.jsx'
import { formatMoney } from '../../lib/format.js'
import { makeAuth } from '../../test/auth.js'

const variant = (id, storage, color, price = '41990000.00', stock = 3) => ({
  ProductVariantId: id, VariantName: storage, Storage: storage, Color: color, Price: price,
  StockQuantity: stock, IsActive: true, Sku: `SKU-${id}`,
})
const product = {
  ProductId: 'p1', Slug: 'san-pham-kiem-thu', Name: 'Điện thoại kiểm thử', CategoryId: 'c1', BrandId: 'b1',
  Brand: { Name: 'Apple', Slug: 'apple' }, Category: { Name: 'Điện thoại', Slug: 'dien-thoai' },
  AverageRating: '4.5', ReviewCount: 3, SoldQuantity: 12, WarrantyMonths: 12,
  Description: 'Đoạn mô tả thứ nhất.\n\nĐoạn mô tả thứ hai.',
  Specifications: { 'Màn hình': '6.9 inch', Chip: 'Chip từ API', 'Bộ nhớ': '256GB', NFC: true, 'Kết nối': ['5G', 'Wi-Fi'], Extra: { Info: 'Có từ API' } },
  Variants: [variant('red256', '256GB', 'Đỏ Burgundy'), variant('black256', '256GB', 'Đen', '42990000.00', 2),
    variant('black512', '512GB', 'Đen', '45990000.00', 1), variant('silver1tb', '1TB', 'Bạc', '50990000.00', 0)],
  Images: [{ ProductImageId: 'i1', ImageUrl: '/first.png', IsDefault: true, DisplayOrder: 0 },
    { ProductImageId: 'i2', ImageUrl: '/second.png', IsDefault: false, DisplayOrder: 1 }],
}

function mockApi({ detail = product, productStatus = 200, cartStatus = 200, relatedStatus = 200, holdCart = false } = {}) {
  const calls = []
  let quantities = [], resolveCart
  const addGate = new Promise((resolve) => { resolveCart = resolve })
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost')
    const endpoint = url.pathname.replace(/^\/api/, '')
    const method = options.method ?? 'GET'
    const body = options.body ? JSON.parse(options.body) : null
    calls.push({ endpoint, method, body, token: options.headers?.Authorization, query: Object.fromEntries(url.searchParams) })
    let result, status = 200
    if (endpoint === '/products/slug/san-pham-kiem-thu') {
      result = productStatus === 200 ? detail : { detail: 'Lỗi tải sản phẩm' }; status = productStatus
    } else if (endpoint === '/products') {
      status = relatedStatus
      result = status === 200 ? { Items: [product, { ProductId: 'p2' }], Total: 2 } : { detail: 'Không tải được sản phẩm tương tự' }
    } else if (endpoint === '/products/p2') result = { ...product, ProductId: 'p2', Slug: 'san-pham-khac', Name: 'Sản phẩm khác' }
    else if (endpoint === '/products/p1/reviews') result = { Items: [], Total: 0, Page: Number(url.searchParams.get('page')), PageSize: Number(url.searchParams.get('page_size')) }
    else if (endpoint === '/cart/items' && method === 'POST') {
      if (holdCart) await addGate
      status = cartStatus
      if (status === 200) quantities = [{ ProductVariantId: body.ProductVariantId, Quantity: 1 }]
      result = status === 200 ? { Items: quantities } : { detail: 'Tồn kho vừa thay đổi, vui lòng thử lại.' }
    } else if (endpoint === '/cart') result = { Items: quantities, SelectedQuantity: quantities.length, SelectedSubtotal: '41990000' }
    else if (endpoint === '/wishlist/items') result = {}
    else if (endpoint.endsWith('/notifications/unread-count')) result = { Count: 0 }
    else if (endpoint === '/conversations' && method === 'POST') result = { ConversationId: 'chat1', Status: 'Open', Mode: 'Staff' }
    else if (endpoint === '/conversations') result = { Items: [], Total: 0 }
    else if (endpoint === '/conversations/chat1') result = { ConversationId: 'chat1', Status: 'Open', Messages: [] }
    else { status = 404; result = { detail: 'Không tìm thấy' } }
    return new Response(JSON.stringify(result), { status, headers: { 'Content-Type': 'application/json' } })
  }))
  return { calls, resolveCart }
}

function renderProduct({ guest = false } = {}) {
  const router = createMemoryRouter(appRoutes, { initialEntries: ['/san-pham/san-pham-kiem-thu'] })
  render(<AuthContext.Provider value={makeAuth({ role: guest ? null : 'Customer' })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

afterEach(() => vi.unstubAllGlobals())

test('real product metadata, breadcrumbs and demo offers are distinguished', async () => {
  mockApi(); renderProduct()
  expect(await screen.findByRole('heading', { level: 1, name: product.Name })).toBeInTheDocument()
  const crumbs = screen.getByRole('navigation', { name: 'Đường dẫn sản phẩm' })
  expect(within(crumbs).getByRole('link', { name: 'Điện thoại' })).toHaveAttribute('href', '/danh-muc/dien-thoai')
  expect(within(crumbs).getByRole('link', { name: 'Apple' })).toHaveAttribute('href', '/thuong-hieu/apple')
  expect(screen.queryByText(/Mã SP:/)).not.toBeInTheDocument()
  expect(screen.getByText('Nội dung demo')).toBeInTheDocument()
  expect(screen.queryByText(/A20 Pro/)).not.toBeInTheDocument()
  expect(screen.queryByText(/Giảm 20%/)).not.toBeInTheDocument()
})

test('version/color combinations update price, specifications and the exact cart payload', async () => {
  const { calls } = mockApi(); renderProduct(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '512GB' }))
  expect(screen.getByRole('button', { name: 'Đỏ Burgundy' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Đen' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: '512GB' })).toHaveAttribute('aria-pressed', 'true')
  expect(document.querySelector('.pd-price')).toHaveTextContent(formatMoney('45990000').replace(/\s/g, ' '))
  const specs = screen.getByRole('region', { name: 'Thông số kỹ thuật' })
  expect(within(specs).getByRole('cell', { name: '512GB' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Thêm vào giỏ hàng' }))
  expect(await screen.findByText('Đã thêm vào giỏ hàng.')).toBeInTheDocument()
  expect(calls.find((call) => call.endpoint === '/cart/items')).toMatchObject({ method: 'POST', token: 'Bearer access-for-test', body: { ProductVariantId: 'black512', Quantity: 1 } })
  expect(await screen.findByText(', 1 sản phẩm')).toBeInTheDocument()
})

test('out of stock and absent price disable both purchase actions', async () => {
  mockApi(); renderProduct(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '1TB' }))
  expect(screen.getByRole('button', { name: 'MUA NGAY' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Thêm vào giỏ hàng' })).toBeDisabled()
  expect(screen.getByText('Hết hàng')).toBeInTheDocument()
})

test('missing variant, images and specifications remain readable without fabricated prices', async () => {
  mockApi({ detail: { ...product, Variants: null, Images: null, Specifications: null, Description: null } }); renderProduct()
  await screen.findByRole('heading', { level: 1, name: product.Name })
  expect(screen.getByText('Chưa có ảnh sản phẩm')).toBeInTheDocument()
  expect(screen.getByText('Đang cập nhật giá')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'MUA NGAY' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Xem đầy đủ thông số' })).toBeDisabled()
})

test('null price on an otherwise available SKU cannot be purchased', async () => {
  mockApi({ detail: { ...product, Variants: [{ ...product.Variants[0], Price: null }] } }); renderProduct()
  await screen.findByRole('heading', { level: 1, name: product.Name })
  expect(screen.getByText('Đang cập nhật giá')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thêm vào giỏ hàng' })).toBeDisabled()
})

test('thumbnail, image modal and full specifications modal use the current product and close', async () => {
  mockApi(); renderProduct(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Xem ảnh 2' }))
  const main = screen.getByRole('button', { name: `Phóng to ảnh ${product.Name}` })
  expect(within(main).getByRole('img')).toHaveAttribute('src', '/second.png')
  await user.click(main)
  expect(screen.getByRole('dialog', { name: product.Name })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Đóng cửa sổ' }))
  await user.click(screen.getByRole('button', { name: 'Xem đầy đủ thông số' }))
  const modal = screen.getByRole('dialog', { name: `Thông số kỹ thuật — ${product.Name}` })
  expect(within(modal).getByRole('cell', { name: 'Info: Có từ API' })).toBeInTheDocument()
  fireEvent(modal, new Event('cancel', { bubbles: true, cancelable: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

test('broken product image falls back without replacing it with a sample photo', async () => {
  mockApi(); renderProduct()
  const main = await screen.findByRole('button', { name: `Phóng to ảnh ${product.Name}` })
  fireEvent.error(within(main).getByRole('img'))
  expect(within(main).getByText('Ảnh sản phẩm đang được cập nhật')).toBeInTheDocument()
})

test('buy now adds the selected SKU before opening the existing cart, without creating an order', async () => {
  const { calls } = mockApi(); const router = renderProduct(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'MUA NGAY' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/gio-hang'))
  expect(calls.find((call) => call.endpoint === '/cart/items').body.ProductVariantId).toBe('red256')
  expect(calls.some((call) => call.endpoint === '/orders')).toBe(false)
})

test('buy failure stays on the product and displays the backend business error', async () => {
  mockApi({ cartStatus: 409 }); const router = renderProduct(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'MUA NGAY' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Tồn kho vừa thay đổi')
  expect(router.state.location.pathname).toBe('/san-pham/san-pham-kiem-thu')
})

test('pending purchase blocks repeat requests and SKU changes', async () => {
  const { calls, resolveCart } = mockApi({ holdCart: true }); renderProduct(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' }))
  expect(screen.getByRole('button', { name: '512GB' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Thêm vào giỏ hàng' }))
  expect(calls.filter((call) => call.endpoint === '/cart/items')).toHaveLength(1)
  await act(async () => resolveCart())
  expect(await screen.findByText('Đã thêm vào giỏ hàng.')).toBeInTheDocument()
})

test('guest cart action asks for an account and signing in returns to the product', async () => {
  const { calls } = mockApi(); const router = renderProduct({ guest: true }); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' }))
  const prompt = await screen.findByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })
  expect(router.state.location.pathname).toBe('/san-pham/san-pham-kiem-thu')
  expect(within(prompt).getByRole('link', { name: 'Đăng ký' })).toHaveAttribute('href', '/dang-ky?next=%2Fsan-pham%2Fsan-pham-kiem-thu')
  expect(within(prompt).getByRole('link', { name: 'Đăng nhập' })).toHaveFocus()
  await user.click(within(prompt).getByRole('link', { name: 'Đăng nhập' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/dang-nhap'))
  expect(router.state.location.search).toBe('?next=%2Fsan-pham%2Fsan-pham-kiem-thu')
  expect(calls.some((call) => call.endpoint === '/cart/items')).toBe(false)
})

test('guest buy-now asks for an account and can be dismissed without leaving the product', async () => {
  const { calls } = mockApi(); const router = renderProduct({ guest: true }); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'MUA NGAY' }))
  const prompt = await screen.findByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })
  fireEvent(prompt, new Event('cancel', { cancelable: true }))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })).not.toBeInTheDocument())
  await user.click(screen.getByRole('button', { name: 'MUA NGAY' }))
  fireEvent.click(await screen.findByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' }))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })).not.toBeInTheDocument())
  expect(router.state.location.pathname).toBe('/san-pham/san-pham-kiem-thu')
  expect(calls.some((call) => call.endpoint === '/cart/items')).toBe(false)
})

test('guest review writing uses the existing account choice and preserves the product return URL', async () => {
  const { calls } = mockApi(); const router = renderProduct({ guest: true }); const user = userEvent.setup()
  expect(await screen.findByRole('link', { name: 'Chưa có đánh giá' }, { timeout: 5000 })).toHaveAttribute('href', '#product-reviews')
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  const prompt = await screen.findByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })
  expect(within(prompt).getByRole('link', { name: 'Đăng nhập' })).toHaveAttribute('href', '/dang-nhap?next=%2Fsan-pham%2Fsan-pham-kiem-thu')
  expect(router.state.location.pathname).toBe('/san-pham/san-pham-kiem-thu')
  expect(calls.some((call) => call.endpoint === '/orders' || call.endpoint === '/reviews')).toBe(false)
})

test('a signed-in staff account is still sent to the sign-in page', async () => {
  const { calls } = mockApi()
  const router = createMemoryRouter(appRoutes, { initialEntries: ['/san-pham/san-pham-kiem-thu'] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Staff' })}><RouterProvider router={router} /></AuthContext.Provider>)
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/dang-nhap'))
  expect(screen.queryByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })).not.toBeInTheDocument()
  expect(calls.some((call) => call.endpoint === '/cart/items')).toBe(false)
})

test('consultation opens the existing employee conversation', async () => {
  const { calls } = mockApi(); renderProduct(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Tư vấn ngay' }))
  expect(await screen.findByRole('dialog', { name: /Chat với nhân viên/ })).toBeInTheDocument()
  await waitFor(() => expect(calls.some((call) => call.endpoint === '/conversations')).toBe(true))
})

test('guest consultation requires sign-in or registration like purchase actions', async () => {
  const { calls } = mockApi(); const router = renderProduct({ guest: true }); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Tư vấn ngay' }))
  expect(await screen.findByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })).toBeInTheDocument()
  expect(calls.some((call) => call.endpoint === '/conversations')).toBe(false)
  await user.click(screen.getByRole('link', { name: 'Đăng ký' }))
  expect(router.state.location.pathname).toBe('/dang-ky')
  expect(router.state.location.search).toBe('?next=%2Fsan-pham%2Fsan-pham-kiem-thu')
})

test('related products exclude the current product and link to their own slug', async () => {
  mockApi(); renderProduct()
  expect(await screen.findByRole('link', { name: /Sản phẩm khác/ })).toHaveAttribute('href', '/san-pham/san-pham-khac')
  const related = screen.getByRole('region', { name: 'Sản phẩm tương tự' })
  expect(within(related).getAllByRole('article')).toHaveLength(1)
})

test.each([404, 500])('product HTTP %s distinguishes not found from retryable failures', async (status) => {
  mockApi({ productStatus: status }); renderProduct()
  if (status === 404) expect(await screen.findByRole('heading', { name: 'Không tìm thấy sản phẩm' })).toBeInTheDocument()
  else expect(await screen.findByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
})

test('related-list failure remains retryable while product purchase stays available', async () => {
  mockApi({ relatedStatus: 503 }); renderProduct()
  const related = await screen.findByRole('region', { name: 'Sản phẩm tương tự' })
  expect(await within(related).findByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'MUA NGAY' })).toBeEnabled()
})
