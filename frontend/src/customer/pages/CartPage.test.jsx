import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { formatMoney } from '../../lib/format.js'
import { appRoutes } from '../../routes.jsx'
import { makeAuth } from '../../test/auth.js'
import { checkoutBlock, lineStatus } from '../components/cart/cartLines.js'

// Text as the default Testing Library normalizer sees it (Intl puts a no-break space before "₫").
const vnd = (value) => formatMoney(value).replace(/\s/g, ' ')

function line(overrides = {}) {
  return {
    CartItemId: 'ci1', ProductVariantId: 'v1', ProductId: 'p1', ProductName: 'iPhone 18 Pro Max', VariantName: '256GB Đỏ',
    Sku: 'IP18-256', Quantity: 1, UnitPrice: '41990000.00', CurrentPrice: '41990000.00', IsSelected: true,
    StockQuantity: 10, AddedAt: '2026-10-13T00:00:00Z', ...overrides,
  }
}

function product(id, variants, overrides = {}) {
  return {
    ProductId: id, Name: `Sản phẩm ${id}`, Slug: `san-pham-${id}`, Status: 'Active', AverageRating: '0', ReviewCount: 0,
    Images: [
      { ProductImageId: `${id}-2`, ImageUrl: `https://cdn.test/${id}-2.png`, DisplayOrder: 2, IsDefault: false },
      { ProductImageId: `${id}-1`, ImageUrl: `https://cdn.test/${id}-1.png`, DisplayOrder: 1, IsDefault: true },
    ],
    Variants: variants, ...overrides,
  }
}

// A cart server with the backend's rules: quantity ≤ stock, totals from the current price over selected lines that
// can be bought, every change returning the whole cart. `sellable: false` marks a withdrawn variant. `coupons`:
// {CODE: {percent, min}}, previewed on the selected lines like the backend; `publicCoupons` is the GET /coupons list.
// `intercept(call)` may answer a request first (an error or a pending promise).
function fakeServer({ lines = [], products = {}, coupons = {}, publicCoupons = [], intercept } = {}) {
  const state = { lines: lines.map((item) => ({ ...item })) }
  const calls = []
  const reply = (status, data) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

  function summary() {
    const items = state.lines.map(({ sellable = true, ...item }) => ({
      ...item,
      LineTotal: (Number(item.CurrentPrice) * item.Quantity).toFixed(2),
      IsAvailable: sellable && item.Quantity <= item.StockQuantity,
    }))
    const chosen = items.filter((item) => item.IsSelected && item.IsAvailable)
    return {
      CartId: 'cart1', CreatedAt: '2026-10-13T00:00:00Z', UpdatedAt: '2026-10-13T00:00:00Z', Items: items,
      SelectedQuantity: chosen.reduce((sum, item) => sum + item.Quantity, 0),
      SelectedSubtotal: chosen.reduce((sum, item) => sum + Number(item.LineTotal), 0).toFixed(2),
    }
  }

  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost')
    const endpoint = url.pathname.replace(/^\/api/, '')
    const method = options.method ?? 'GET'
    const body = options.body ? JSON.parse(options.body) : null
    const call = { endpoint, method, body, query: Object.fromEntries(url.searchParams), token: options.headers?.Authorization }
    calls.push(call)
    const early = await intercept?.(call, state)
    if (early) return early

    const itemId = endpoint.match(/^\/cart\/items\/([^/]+)$/)?.[1]
    const found = itemId && state.lines.find((item) => item.CartItemId === itemId)
    if (endpoint === '/users/me/notifications/unread-count') return reply(200, { Count: 0 })
    if (endpoint === '/cart' && method === 'GET') return reply(200, summary())
    if (endpoint === '/coupons') return reply(200, publicCoupons)
    if (endpoint === '/cart/coupon-preview') {
      const cart = summary()
      if (!cart.Items.some((item) => item.IsSelected && item.IsAvailable)) {
        return reply(400, { detail: 'Giỏ hàng chưa có sản phẩm được chọn', code: 'cart_empty' })
      }
      const [code, rule] = Object.entries(coupons).find(([name]) => name.toLowerCase() === call.query.code.toLowerCase()) ?? []
      if (!code) return reply(400, { detail: 'Mã giảm giá không hợp lệ', code: 'coupon_invalid' })
      const subtotal = Number(cart.SelectedSubtotal)
      if (subtotal < rule.min) {
        return reply(400, { detail: 'Đơn hàng chưa đạt giá trị tối thiểu của mã giảm giá', code: 'coupon_min_order_value' })
      }
      return reply(200, { Code: code, PromotionId: 'promo1', Subtotal: cart.SelectedSubtotal,
        EligibleSubtotal: cart.SelectedSubtotal, DiscountAmount: (subtotal * rule.percent / 100).toFixed(2) })
    }
    if (endpoint === '/cart/selection' && method === 'PUT') {
      state.lines.forEach((item) => { item.IsSelected = body.IsSelected })
      return reply(200, summary())
    }
    if (itemId && !found) return reply(404, { detail: 'Không tìm thấy sản phẩm trong giỏ hàng', code: 'cart_item_not_found' })
    if (itemId && method === 'PATCH') {
      if ('Quantity' in body && body.Quantity > found.StockQuantity) {
        return reply(400, { detail: `Số lượng vượt tồn kho hiện có (${found.StockQuantity})`, code: 'insufficient_stock' })
      }
      Object.assign(found, body)
      return reply(200, summary())
    }
    if (itemId && method === 'DELETE') {
      state.lines = state.lines.filter((item) => item !== found)
      return reply(200, summary())
    }
    const productId = endpoint.match(/^\/products\/([^/]+)$/)?.[1]
    if (productId && products[productId]) return reply(200, products[productId])
    return reply(404, { detail: 'Không tìm thấy sản phẩm', code: 'product_not_found' })
  }))
  return {
    calls, state,
    writes: () => calls.filter((call) => call.method !== 'GET'),
    // GET /cart from the page and from the header cart entry (CartLink).
    cartReads: () => calls.filter((call) => call.endpoint === '/cart' && call.method === 'GET').length,
  }
}

function renderCart(auth = makeAuth({ role: 'Customer' })) {
  const router = createMemoryRouter(appRoutes, { initialEntries: ['/gio-hang'] })
  render(<AuthContext.Provider value={auth}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

// Counts 'vietech-cart-changed' events; the header cart entry (CartLink) reads GET /cart again on each one.
const cleanups = []
function watchCartChanges() {
  const changes = vi.fn()
  window.addEventListener('vietech-cart-changed', changes)
  cleanups.push(() => window.removeEventListener('vietech-cart-changed', changes))
  return changes
}

const IPHONE = product('p1', [
  { ProductVariantId: 'v1', VariantName: '256GB Đỏ', Color: 'Đỏ', Storage: '256GB', Price: '41990000.00', StockQuantity: 10 },
  { ProductVariantId: 'v2', VariantName: '512GB Đen', Color: null, Storage: null, Price: '45990000.00', StockQuantity: 4 },
])

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
  cleanups.splice(0).forEach((cleanup) => cleanup())
})

describe('cart line rules', () => {
  test('a line is classified from the cart data and its public product detail', () => {
    const detail = product('p1', [{ ProductVariantId: 'v1' }])
    expect(lineStatus({ ...line(), IsAvailable: true }, detail)).toBe('ok')
    expect(lineStatus({ ...line({ Quantity: 10 }), IsAvailable: true }, detail)).toBe('atLimit')
    expect(lineStatus({ ...line({ Quantity: 4, StockQuantity: 2 }), IsAvailable: false }, detail)).toBe('overStock')
    expect(lineStatus({ ...line({ StockQuantity: 0 }), IsAvailable: false }, detail)).toBe('soldOut')
    expect(lineStatus({ ...line({ StockQuantity: 0 }), IsAvailable: false }, null)).toBe('stopped')
    expect(lineStatus({ ...line({ ProductVariantId: 'gone' }), IsAvailable: false }, detail)).toBe('stopped')
    expect(lineStatus({ ...line(), IsAvailable: false }, undefined)).toBe('stopped')
  })

  test('checkout needs a selected line and every selected line buyable', () => {
    expect(checkoutBlock([{ IsSelected: false, IsAvailable: true }])).toMatch(/chọn ít nhất một sản phẩm/)
    expect(checkoutBlock([{ IsSelected: true, IsAvailable: false }])).toMatch(/không thể mua/)
    expect(checkoutBlock([{ IsSelected: true, IsAvailable: true }, { IsSelected: false, IsAvailable: false }])).toBe('')
  })
})

describe('cart page', () => {
  test('shows each line with its product image, variant, price and the server totals', async () => {
    const server = fakeServer({
      lines: [line(), line({ CartItemId: 'ci2', ProductVariantId: 'v2', ProductName: 'iPhone 18 Pro Max 512GB',
        VariantName: '512GB Đen', Quantity: 2,
        CurrentPrice: '45990000.00', UnitPrice: '45990000.00', IsSelected: false, StockQuantity: 4 })],
      products: { p1: IPHONE },
    })
    renderCart()

    const first = await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })
    await waitFor(() => expect(first.querySelector('img')).toHaveAttribute('src', 'https://cdn.test/p1-1.png'))
    expect(within(first).getByText('Đỏ • 256GB')).toBeInTheDocument()
    expect(within(first).getByText(vnd(41990000))).toBeInTheDocument()
    expect(within(first).getByRole('link', { name: 'Xem chi tiết' })).toHaveAttribute('href', '/san-pham/san-pham-p1')
    expect(within(first).getByText('Còn hàng')).toBeInTheDocument()

    const [, second] = screen.getAllByRole('article')
    expect(within(second).getByText('512GB Đen')).toBeInTheDocument() // no colour/storage: the variant name
    expect(within(second).getByText(vnd(91980000))).toBeInTheDocument() // line total for 2
    expect(within(second).getByText('Còn 4 sản phẩm')).toBeInTheDocument()

    const summary = screen.getByRole('complementary', { name: 'Thông tin đơn hàng' })
    expect(within(summary).getByText('1 / 2')).toBeInTheDocument()
    expect(within(summary).getAllByText(vnd(41990000))).toHaveLength(2)
    expect(within(summary).getByRole('link', { name: 'Mua hàng' })).toHaveAttribute('href', '/dat-hang')
    expect(within(summary).getByText('Áp dụng mã giảm giá')).toBeInTheDocument()
    expect(within(summary).getByRole('button', { name: 'Chọn mã giảm giá' })).toBeEnabled()
    expect(within(summary).queryByText(/Phí vận chuyển/)).not.toBeInTheDocument()
    expect(screen.getByText('2 sản phẩm trong giỏ hàng')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Chọn tất cả/ }).indeterminate).toBe(true)
    // Two lines of the same product read its detail once, with the customer token only on the cart.
    expect(server.calls.filter((call) => call.endpoint === '/products/p1')).toHaveLength(1)
    expect(server.calls.find((call) => call.endpoint === '/cart').token).toBe('Bearer access-for-test')
    expect(document.title).toBe('Giỏ hàng | VieTech')
  })

  test('a line on a direct promotion shows its sale price with the original price struck through', async () => {
    // Added before the promotion started, at the price now struck through.
    fakeServer({ lines: [line({ OriginalPrice: '44990000.00', UnitPrice: '44990000.00' })], products: { p1: IPHONE } })
    renderCart()

    const item = await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })
    const price = item.querySelector('.cart-item-price')
    expect(price).toHaveTextContent(vnd(41990000))
    expect(price.querySelector('del')).toHaveTextContent(`Giá gốc ${vnd(44990000)}`)
    expect(within(item).queryByText(/Giá đã thay đổi/)).not.toBeInTheDocument()
  })

  test('each line shows the photo of the colour in the cart, not the default colour', async () => {
    const photo = (url) => ({ ImageUrl: url, DisplayOrder: 1, IsDefault: true })
    fakeServer({
      lines: [line({ ProductVariantId: 'v2', VariantName: '512GB Đen', CurrentPrice: '45990000.00', UnitPrice: '45990000.00' })],
      products: { p1: { ...IPHONE, DefaultVariantId: 'v1',
        VariantImages: { v1: [photo('https://cdn.test/do.png')], v2: [photo('https://cdn.test/den.png')] } } },
    })
    renderCart()

    const item = await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })
    await waitFor(() => expect(item.querySelector('img')).toHaveAttribute('src', 'https://cdn.test/den.png'))
  })

  test('a product that is no longer sold keeps its line with a placeholder image and cannot be bought', async () => {
    fakeServer({ lines: [line({ sellable: false })] })
    renderCart()

    const item = await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })
    expect(await within(item).findByText('Ngừng kinh doanh')).toBeInTheDocument()
    expect(within(item).getByText('VieTech')).toBeInTheDocument()
    expect(within(item).queryByRole('link', { name: 'Xem chi tiết' })).not.toBeInTheDocument()
    expect(within(item).getByRole('button', { name: 'Tăng số lượng iPhone 18 Pro Max' })).toBeDisabled()
    expect(within(item).getByText(/không còn được bán/)).toBeInTheDocument()
    const summary = screen.getByRole('complementary', { name: 'Thông tin đơn hàng' })
    expect(within(summary).getByRole('button', { name: 'Mua hàng' })).toBeDisabled()
    expect(within(summary).getByText(/không thể mua/)).toBeInTheDocument()
    expect(within(summary).getAllByText(vnd(0))).toHaveLength(2)
  })

  test('quantity changes are saved one at a time and the returned cart replaces the screen', async () => {
    let open
    const gate = new Promise((resolve) => { open = resolve })
    const server = fakeServer({
      lines: [line({ StockQuantity: 2 }), line({ CartItemId: 'ci2', ProductVariantId: 'v2', ProductName: 'Galaxy S26' })],
      products: { p1: IPHONE },
      intercept: async (call) => { if (call.method === 'PATCH') await gate },
    })
    const user = userEvent.setup()
    renderCart()

    const item = await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })
    await user.click(within(item).getByRole('button', { name: 'Tăng số lượng iPhone 18 Pro Max' }))
    // While saving, every control of the cart and the checkout button are locked.
    const other = screen.getByRole('article', { name: 'Galaxy S26' })
    expect(within(other).getByRole('button', { name: 'Tăng số lượng Galaxy S26' })).toBeDisabled()
    expect(within(other).getByRole('checkbox', { name: 'Chọn Galaxy S26' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Mua hàng' })).toBeDisabled()
    open()

    expect(await within(item).findByText(/Bạn đã chọn tối đa số lượng hiện có/)).toBeInTheDocument()
    expect(within(item).getByRole('textbox', { name: 'Số lượng iPhone 18 Pro Max' })).toHaveValue('2')
    expect(within(item).getByRole('button', { name: 'Tăng số lượng iPhone 18 Pro Max' })).toBeDisabled()
    expect(server.writes()).toEqual([expect.objectContaining({ endpoint: '/cart/items/ci1', method: 'PATCH', body: { Quantity: 2 } })])
    expect(server.calls.filter((call) => call.endpoint === '/products/p1')).toHaveLength(1)
  })

  test('a typed quantity is clamped to the stock and sent on Enter', async () => {
    const server = fakeServer({ lines: [line({ StockQuantity: 3 })], products: { p1: IPHONE } })
    const user = userEvent.setup()
    renderCart()

    const input = await screen.findByRole('textbox', { name: 'Số lượng iPhone 18 Pro Max' })
    await user.clear(input)
    await user.type(input, '99{Enter}')
    await waitFor(() => expect(input).toHaveValue('3'))
    expect(server.writes()).toEqual([expect.objectContaining({ method: 'PATCH', body: { Quantity: 3 } })])

    await user.clear(input)
    await user.type(input, '{Escape}')
    await user.tab()
    expect(input).toHaveValue('3')
    expect(server.writes()).toHaveLength(1)
  })

  test('selecting lines, selecting all and removing use the cart API', async () => {
    const server = fakeServer({
      lines: [line(), line({ CartItemId: 'ci2', ProductVariantId: 'v2', ProductName: 'Galaxy S26', IsSelected: false })],
      products: { p1: IPHONE },
    })
    const changes = watchCartChanges()
    const user = userEvent.setup()
    renderCart()

    const selectAll = await screen.findByRole('checkbox', { name: /Chọn tất cả \(2 sản phẩm\)/ })
    await user.click(selectAll)
    await waitFor(() => expect(selectAll).toBeChecked())
    await user.click(screen.getByRole('checkbox', { name: 'Chọn iPhone 18 Pro Max' }))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Chọn iPhone 18 Pro Max' })).not.toBeChecked())
    await user.click(screen.getByRole('button', { name: 'Xóa Galaxy S26 khỏi giỏ hàng' }))
    await waitFor(() => expect(screen.queryByRole('article', { name: 'Galaxy S26' })).not.toBeInTheDocument())

    expect(server.writes().map(({ endpoint, method, body }) => [method, endpoint, body])).toEqual([
      ['PUT', '/cart/selection', { IsSelected: true }],
      ['PATCH', '/cart/items/ci1', { IsSelected: false }],
      ['DELETE', '/cart/items/ci2', null],
    ])
    // Changes never reload the cart: the response of each one is shown. Each change tells the header, whose cart
    // entry (CartLink) reads the cart once on mount and once per change.
    expect(changes).toHaveBeenCalledTimes(3)
    await waitFor(() => expect(server.cartReads()).toBe(1 + 1 + 3))
    expect(screen.getByRole('button', { name: 'Mua hàng' })).toBeDisabled()
    expect(screen.getByText('Hãy chọn ít nhất một sản phẩm để mua hàng.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Xóa iPhone 18 Pro Max khỏi giỏ hàng' }))
    expect(await screen.findByRole('heading', { name: 'Giỏ hàng đang trống' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Tiếp tục mua sắm' })).toHaveAttribute('href', '/')
  })

  test('a stock conflict shows the server message and reloads the cart', async () => {
    const server = fakeServer({
      lines: [line({ StockQuantity: 5 })],
      products: { p1: IPHONE },
      // Someone bought the rest after the page loaded.
      intercept: (call, state) => { if (call.method === 'PATCH') state.lines[0].StockQuantity = 1 },
    })
    const user = userEvent.setup()
    renderCart()

    const item = await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })
    await user.click(within(item).getByRole('button', { name: 'Tăng số lượng iPhone 18 Pro Max' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Số lượng vượt tồn kho hiện có (1)')
    expect(await within(item).findByText('Còn 1 sản phẩm')).toBeInTheDocument()
    // The page read it twice (load, reload after the conflict); the header once on mount and once after the reload.
    await waitFor(() => expect(server.cartReads()).toBe(2 + 2))
  })

  test('the header cart count follows every saved change', async () => {
    fakeServer({ lines: [line({ StockQuantity: 5 })], products: { p1: IPHONE } })
    const user = userEvent.setup()
    renderCart()

    const header = screen.getByRole('navigation', { name: 'Tài khoản' })
    expect(await within(header).findByRole('link', { name: 'Giỏ hàng, 1 sản phẩm' })).toHaveAttribute('href', '/gio-hang')
    const item = await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })
    await user.click(within(item).getByRole('button', { name: 'Tăng số lượng iPhone 18 Pro Max' }))
    expect(await within(header).findByRole('link', { name: 'Giỏ hàng, 2 sản phẩm' })).toBeInTheDocument()
    await user.click(within(item).getByRole('button', { name: 'Xóa iPhone 18 Pro Max khỏi giỏ hàng' }))
    expect(await within(header).findByRole('link', { name: 'Giỏ hàng' })).toBeInTheDocument()
  })

  test('a line above the stock can be reduced to the stock in one step', async () => {
    const server = fakeServer({ lines: [line({ Quantity: 5, StockQuantity: 2 })], products: { p1: IPHONE } })
    const user = userEvent.setup()
    renderCart()

    const item = await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })
    expect(within(item).getByText('Vượt tồn kho')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mua hàng' })).toBeDisabled()
    await user.click(within(item).getByRole('button', { name: 'Giảm còn 2' }))
    await waitFor(() => expect(screen.getByRole('link', { name: 'Mua hàng' })).toHaveAttribute('href', '/dat-hang'))
    expect(server.writes()).toEqual([expect.objectContaining({ body: { Quantity: 2 } })])
  })

  test('a failed load can be retried', async () => {
    // Down until the retry (the header cart entry reads the same endpoint, so no call count is used).
    let down = true
    fakeServer({
      lines: [line()],
      intercept: (call) => call.endpoint === '/cart' && down
        ? new Response(JSON.stringify({ detail: 'Internal Server Error' }), { status: 500 }) : undefined,
    })
    const user = userEvent.setup()
    renderCart()

    expect(await screen.findByRole('heading', { name: 'Không thể tải giỏ hàng' })).toBeInTheDocument()
    down = false
    await user.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('article', { name: 'iPhone 18 Pro Max' })).toBeInTheDocument()
  })

  test('guests sign in first and come back to the cart', async () => {
    const server = fakeServer()
    const router = renderCart(makeAuth())
    await waitFor(() => expect(router.state.location.pathname).toBe('/dang-nhap'))
    expect(router.state.location.search).toBe('?next=%2Fgio-hang')
    expect(server.calls.some((call) => call.endpoint === '/cart')).toBe(false)
  })
})

describe('cart coupon', () => {
  const previews = (server) => server.calls.filter((call) => call.endpoint === '/cart/coupon-preview')

  test('a code is checked in the dialog, confirmed, taken off the total and kept for checkout', async () => {
    const server = fakeServer({ lines: [line()], products: { p1: IPHONE }, coupons: { GIAM10: { percent: 10, min: 0 } } })
    const user = userEvent.setup()
    renderCart()

    await user.click(await screen.findByRole('button', { name: 'Chọn mã giảm giá' }))
    const dialog = screen.getByRole('dialog', { name: 'Nhập hoặc chọn mã khuyến mãi' })
    expect(within(dialog).getByRole('textbox', { name: 'Mã khuyến mãi' })).toHaveFocus()
    expect(within(dialog).getByRole('button', { name: 'Áp dụng' })).toBeDisabled()
    expect(await within(dialog).findByText(/Hiện chưa có mã khuyến mãi nào để chọn/)).toBeInTheDocument()
    await user.type(within(dialog).getByRole('textbox', { name: 'Mã khuyến mãi' }), ' giam10 ')
    await user.click(within(dialog).getByRole('button', { name: 'Áp dụng' }))
    expect(await within(dialog).findByText('GIAM10')).toBeInTheDocument()
    expect(within(dialog).getByText(vnd(4199000))).toBeInTheDocument()
    expect(previews(server)).toEqual([expect.objectContaining({ query: { code: 'giam10' }, token: 'Bearer access-for-test' })])

    await user.click(within(dialog).getByRole('button', { name: 'Xác nhận' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const summary = screen.getByRole('complementary', { name: 'Thông tin đơn hàng' })
    expect(within(summary).getByText('GIAM10')).toBeInTheDocument()
    expect(within(summary).getByText('Giảm giá').nextElementSibling).toHaveTextContent(`−${vnd(4199000)}`)
    expect(within(summary).getByText(vnd(37791000))).toBeInTheDocument()
    expect(within(summary).getByRole('link', { name: 'Mua hàng' })).toHaveAttribute('href', '/dat-hang')
    expect(sessionStorage.getItem('vietech-cart-coupon:Customer-id')).toBe('GIAM10')
    // The confirmed preview is used as it is, not requested again.
    expect(previews(server)).toHaveLength(1)

    await user.click(within(summary).getByRole('button', { name: 'Đổi mã giảm giá' }))
    const again = screen.getByRole('dialog', { name: 'Nhập hoặc chọn mã khuyến mãi' })
    expect(within(again).getByRole('textbox', { name: 'Mã khuyến mãi' })).toHaveValue('GIAM10')
    await user.click(within(again).getByRole('button', { name: 'Bỏ mã đang dùng' }))
    expect(within(summary).getByText('Áp dụng mã giảm giá')).toBeInTheDocument()
    expect(within(summary).queryByText('Giảm giá')).not.toBeInTheDocument()
    expect(sessionStorage.getItem('vietech-cart-coupon:Customer-id')).toBeNull()
  })

  test('public coupons are listed to choose from; one the selection does not reach yet cannot be chosen', async () => {
    const offer = (code, overrides) => ({ CouponId: code, Code: code, Name: `Ưu đãi ${code}`, DiscountType: 'Percentage',
      DiscountValue: '10.00', MinOrderValue: '0.00', MaxDiscountAmount: null, EndDate: '2026-12-31T16:59:59Z',
      RemainingUses: 5, ...overrides })
    const server = fakeServer({
      lines: [line()], products: { p1: IPHONE }, coupons: { GIAM10: { percent: 10, min: 0 } },
      publicCoupons: [offer('GIAM10', { MaxDiscountAmount: '5000000.00' }), offer('VIP', { DiscountType: 'FixedAmount',
        DiscountValue: '2000000.00', MinOrderValue: '50000000.00', RemainingUses: null })],
    })
    const user = userEvent.setup()
    renderCart()

    await user.click(await screen.findByRole('button', { name: 'Chọn mã giảm giá' }))
    const dialog = screen.getByRole('dialog', { name: 'Nhập hoặc chọn mã khuyến mãi' })
    const list = await within(dialog).findByRole('list', { name: 'Mã khuyến mãi có thể chọn' })
    const [first, second] = within(list).getAllByRole('listitem')
    expect(first).toHaveTextContent('Giảm 10%')
    expect(first).toHaveTextContent(`Mọi đơn hàng · Giảm tối đa ${vnd(5000000)}`)
    expect(first).toHaveTextContent('Còn 5 lượt')
    expect(second).toHaveTextContent(`Giảm ${vnd(2000000)}`)
    expect(second).toHaveTextContent(`Mua thêm ${vnd(8010000)} để dùng mã này`) // 50 000 000 − 41 990 000 đã chọn
    expect(within(second).getByRole('button', { name: 'Chọn mã VIP' })).toBeDisabled()
    // The list is public: it is read without the customer's token.
    expect(server.calls.find((call) => call.endpoint === '/coupons').token).toBeUndefined()

    await user.click(within(first).getByRole('button', { name: 'Chọn mã GIAM10' }))
    expect(await within(dialog).findByText(/cho các sản phẩm đã chọn/)).toBeInTheDocument()
    expect(within(dialog).getByRole('textbox', { name: 'Mã khuyến mãi' })).toHaveValue('GIAM10')
    expect(within(first).getByRole('button', { name: 'Chọn mã GIAM10' })).toHaveAttribute('aria-pressed', 'true')
    expect(previews(server)).toEqual([expect.objectContaining({ query: { code: 'GIAM10' } })])

    await user.click(within(dialog).getByRole('button', { name: 'Xác nhận' }))
    const summary = screen.getByRole('complementary', { name: 'Thông tin đơn hàng' })
    expect(within(summary).getByText('GIAM10')).toBeInTheDocument()
    expect(within(summary).getByText('Giảm giá').nextElementSibling).toHaveTextContent(`−${vnd(4199000)}`)
    expect(previews(server)).toHaveLength(1)
  })

  test('a wrong code shows the server message, keeps the dialog open and closing changes nothing', async () => {
    fakeServer({ lines: [line()], products: { p1: IPHONE } })
    const user = userEvent.setup()
    renderCart()

    await user.click(await screen.findByRole('button', { name: 'Chọn mã giảm giá' }))
    const dialog = screen.getByRole('dialog', { name: 'Nhập hoặc chọn mã khuyến mãi' })
    await user.type(within(dialog).getByRole('textbox', { name: 'Mã khuyến mãi' }), 'SAIMA')
    await user.click(within(dialog).getByRole('button', { name: 'Xác nhận' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Mã giảm giá không hợp lệ')
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Đóng' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('Áp dụng mã giảm giá')).toBeInTheDocument()
    expect(sessionStorage.getItem('vietech-cart-coupon:Customer-id')).toBeNull()
  })

  test('a kept code is checked again when the selection changes and blocks the order once it stops applying', async () => {
    sessionStorage.setItem('vietech-cart-coupon:Customer-id', 'MIN50')
    const server = fakeServer({
      lines: [line(), line({ CartItemId: 'ci2', ProductVariantId: 'v2', ProductName: 'Xiaomi 17T Pro', CurrentPrice: '21490000.00' })],
      products: { p1: IPHONE },
      coupons: { MIN50: { percent: 5, min: 50000000 } },
    })
    const user = userEvent.setup()
    renderCart()

    const summary = await screen.findByRole('complementary', { name: 'Thông tin đơn hàng' })
    await waitFor(() => expect(within(summary).getByText('Giảm giá').nextElementSibling).toHaveTextContent(`−${vnd(3174000)}`))
    expect(within(summary).getByText(vnd(60306000))).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: 'Chọn Xiaomi 17T Pro' }))
    expect(await within(summary).findByRole('alert')).toHaveTextContent('Đơn hàng chưa đạt giá trị tối thiểu của mã giảm giá')
    expect(within(summary).getByRole('button', { name: 'Mua hàng' })).toBeDisabled()
    expect(within(summary).getByText('Mã giảm giá MIN50 không dùng được. Hãy đổi hoặc bỏ mã.')).toBeInTheDocument()
    expect(previews(server)).toHaveLength(2)

    await user.click(within(summary).getByRole('button', { name: 'Bỏ mã' }))
    expect(within(summary).getByText('Áp dụng mã giảm giá')).toBeInTheDocument()
    expect(within(summary).getByRole('link', { name: 'Mua hàng' })).toHaveAttribute('href', '/dat-hang')
    expect(sessionStorage.getItem('vietech-cart-coupon:Customer-id')).toBeNull()
  })

  test('a coupon check that fails on the server is not called invalid and can be tried again', async () => {
    sessionStorage.setItem('vietech-cart-coupon:Customer-id', 'GIAM10')
    let failures = 1
    const server = fakeServer({
      lines: [line()], products: { p1: IPHONE }, coupons: { GIAM10: { percent: 10, min: 0 } },
      intercept: (call) => call.endpoint === '/cart/coupon-preview' && failures-- > 0
        ? new Response(JSON.stringify({ detail: 'Service Unavailable' }), { status: 503 }) : undefined,
    })
    const user = userEvent.setup()
    renderCart()

    const summary = await screen.findByRole('complementary', { name: 'Thông tin đơn hàng' })
    const alert = await within(summary).findByRole('alert')
    expect(alert).toHaveTextContent('Chưa kiểm tra được mã giảm giá. Hệ thống đang bận. Vui lòng thử lại sau.')
    expect(alert).not.toHaveTextContent('không dùng được')
    expect(within(summary).getByText('Chưa xác định')).toBeInTheDocument()
    expect(within(summary).getByRole('button', { name: 'Mua hàng' })).toBeDisabled()
    expect(within(summary).getByText('Chưa kiểm tra được mã giảm giá. Hãy thử lại hoặc bỏ mã.')).toBeInTheDocument()

    await user.click(within(alert).getByRole('button', { name: 'Thử lại' }))
    await waitFor(() => expect(within(summary).getByText('Giảm giá').nextElementSibling).toHaveTextContent(`−${vnd(4199000)}`))
    expect(within(summary).getByRole('link', { name: 'Mua hàng' })).toHaveAttribute('href', '/dat-hang')
    expect(previews(server)).toHaveLength(2)
  })
})
