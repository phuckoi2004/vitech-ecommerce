import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { toProductCard } from '../../lib/catalog-api.js'
import { makeAuth } from '../../test/auth.js'
import { WishlistPage } from '../pages/CustomerLists.jsx'
import ProductCard from './ProductCard.jsx'

const detail = { ProductId: 'p1', Name: 'Điện thoại kiểm thử', Slug: 'dien-thoai-kiem-thu', AverageRating: '4.5', ReviewCount: 2,
  SoldQuantity: 5, Images: [{ ProductImageId: 'photo1', ImageUrl: '/phone.png', IsDefault: true, DisplayOrder: 0 }],
  Variants: [{ ProductVariantId: 'v1', VariantName: 'Đen · 256GB', Price: '12000000', StockQuantity: 3, IsActive: true }] }
const product = toProductCard(detail)

function mockApi({ added = false, deleteFailure = false, productDetail = detail, productStatus = 200, holdCart = false, cartFailure = false } = {}) {
  let ids = added ? ['p1'] : [], heldRead = null, reads = 0
  const calls = []
  let releaseCart
  const cartGate = new Promise((resolve) => { releaseCart = resolve })
  const controls = { deleteFailure, productStatus, cartFailure, holdNextRead: false, replace: (next) => { ids = next } }
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost'), path = url.pathname.replace(/^\/api/, '')
    const method = options.method ?? 'GET'
    const body = options.body ? JSON.parse(options.body) : null
    calls.push({ path, method, body })
    let data = {}, status = 200
    if (path === '/wishlist' && method === 'GET') {
      reads++
      const snapshot = [...ids]
      if (controls.holdNextRead) {
        controls.holdNextRead = false
        await new Promise((resolve) => { heldRead = resolve })
      }
      const { Variants: _variants, Images: _images, ...summary } = detail
      data = { Items: snapshot.map((id) => ({ WishlistItemId: `wish-${id}`, ProductId: id, Product: summary })) }
    } else if (path === '/products/p1' && method === 'GET') {
      status = controls.productStatus
      data = status === 200 ? productDetail : { detail: 'Không tải được thông tin sản phẩm.' }
    } else if (path === '/cart/items' && method === 'POST') {
      if (holdCart) await cartGate
      status = controls.cartFailure ? 400 : 200
      data = controls.cartFailure ? { detail: 'Số lượng sản phẩm vượt tồn kho.' } : { Items: [] }
    } else if (path === '/wishlist/items' && method === 'POST') {
      if (!ids.includes(body.ProductId)) ids.push(body.ProductId)
      status = 201; data = { WishlistItemId: `wish-${body.ProductId}`, ProductId: body.ProductId }
    } else if (path === '/wishlist/products/p1' && method === 'DELETE') {
      if (controls.deleteFailure) { status = 503; data = { detail: 'Không thể bỏ yêu thích lúc này.' } }
      else { ids = ids.filter((id) => id !== 'p1'); return new Response(null, { status: 204 }) }
    } else { status = 404; data = { detail: 'Không tìm thấy dữ liệu.' } }
    return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
  }))
  return { calls, controls, release: () => heldRead?.(), releaseCart, readCount: () => reads }
}

function show(userId, { route = '/', duplicate = false } = {}) {
  const auth = makeAuth({ role: 'Customer' })
  auth.user.UserId = userId
  return render(<AuthContext.Provider value={auth}><MemoryRouter initialEntries={[route]}>
    <Link to="/">Trang chủ kiểm thử</Link><Link to="/yeu-thich">Danh sách yêu thích kiểm thử</Link>
    <Routes>
      <Route path="/" element={<><ProductCard product={product} />{duplicate && <ProductCard product={product} />}</>} />
      <Route path="/yeu-thich" element={<WishlistPage />} />
      <Route path="/san-pham/dien-thoai-kiem-thu" element={<h1>Chi tiết sản phẩm kiểm thử</h1>} />
    </Routes>
  </MemoryRouter></AuthContext.Provider>)
}

afterEach(() => vi.unstubAllGlobals())

test('liking and unliking synchronize duplicate cards; the heart never navigates to product detail', async () => {
  const { calls } = mockApi(); show('wishlist-duplicates', { duplicate: true }); const user = userEvent.setup()
  const hearts = screen.getAllByRole('button', { name: `Thêm ${detail.Name} vào yêu thích` })
  await user.click(hearts[0])
  await waitFor(() => expect(screen.getAllByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })).toHaveLength(2))
  await user.click(hearts[1])
  await waitFor(() => hearts.forEach((heart) => {
    expect(heart).toHaveAttribute('aria-pressed', 'false')
    expect(heart).not.toHaveClass('is-added')
  }))
  expect(calls.filter((call) => call.method !== 'GET')).toEqual([
    { path: '/wishlist/items', method: 'POST', body: { ProductId: 'p1' } },
    { path: '/wishlist/products/p1', method: 'DELETE', body: null },
  ])
  expect(screen.queryByRole('heading', { name: 'Chi tiết sản phẩm kiểm thử' })).not.toBeInTheDocument()
})

test('the wishlist removes through its heart, stays empty afterwards, and home no longer shows a selected heart', async () => {
  const { calls } = mockApi({ added: true }); show('wishlist-remove-and-return', { route: '/yeu-thich' }); const user = userEvent.setup()
  const heart = await screen.findByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })
  expect(screen.queryByRole('button', { name: 'Xóa khỏi yêu thích' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Xem chi tiết' })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: new RegExp(detail.Name) })).toHaveAttribute('href', '/san-pham/dien-thoai-kiem-thu')
  await user.click(heart)
  expect(await screen.findByRole('heading', { name: 'Bạn chưa có sản phẩm yêu thích nào.' })).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'Trang chủ kiểm thử' }))
  const homeHeart = await screen.findByRole('button', { name: `Thêm ${detail.Name} vào yêu thích` })
  expect(homeHeart).toHaveAttribute('aria-pressed', 'false')
  expect(homeHeart).not.toHaveClass('is-added')
  expect(calls.filter((call) => call.method === 'DELETE')).toHaveLength(1)
})

test('clicking the product card opens detail without needing a second button', async () => {
  mockApi({ added: true }); show('wishlist-product-link', { route: '/yeu-thich' })
  await userEvent.setup().click(await screen.findByRole('link', { name: new RegExp(detail.Name) }))
  expect(await screen.findByRole('heading', { name: 'Chi tiết sản phẩm kiểm thử' })).toBeInTheDocument()
})

test('a failed removal retains the selected heart and the wishlist product', async () => {
  mockApi({ added: true, deleteFailure: true }); show('wishlist-delete-failure', { route: '/yeu-thich' }); const user = userEvent.setup()
  const heart = await screen.findByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })
  await user.click(heart)
  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể bỏ yêu thích lúc này.')
  expect(heart).toHaveAttribute('aria-pressed', 'true')
  expect(heart).toHaveClass('is-added')
  expect(screen.queryByRole('heading', { name: 'Bạn chưa có sản phẩm yêu thích nào.' })).not.toBeInTheDocument()
})

test('returning to the home cards refreshes an older cached wishlist from the server', async () => {
  const { controls, readCount } = mockApi({ added: true }); const first = show('wishlist-refresh')
  await screen.findByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })
  first.unmount(); controls.replace([])
  show('wishlist-refresh')
  await screen.findByRole('button', { name: `Thêm ${detail.Name} vào yêu thích` })
  expect(readCount()).toBe(2)
})

test('an old pending GET cannot turn the heart blue again after successful removal', async () => {
  const api = mockApi({ added: true }); const first = show('wishlist-remove-race')
  await screen.findByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })
  first.unmount(); api.controls.holdNextRead = true
  show('wishlist-remove-race'); const user = userEvent.setup()
  await waitFor(() => expect(api.readCount()).toBe(2))
  await user.click(screen.getByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` }))
  expect(await screen.findByRole('button', { name: `Thêm ${detail.Name} vào yêu thích` })).not.toHaveClass('is-added')
  await act(async () => api.release())
  expect(screen.getByRole('button', { name: `Thêm ${detail.Name} vào yêu thích` })).toHaveAttribute('aria-pressed', 'false')
})

test('an old pending GET cannot erase a like added while that GET was loading', async () => {
  const api = mockApi(); api.controls.holdNextRead = true; show('wishlist-add-race'); const user = userEvent.setup()
  await waitFor(() => expect(api.readCount()).toBe(1))
  await user.click(screen.getByRole('button', { name: `Thêm ${detail.Name} vào yêu thích` }))
  await screen.findByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })
  await act(async () => api.release())
  expect(screen.getByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })).toHaveClass('is-added')
})

test('wishlist summaries are enriched with real price/photo/stock before rendering, without a false sold-out badge', async () => {
  const { calls } = mockApi({ added: true }); show('wishlist-real-stock', { route: '/yeu-thich' })
  await screen.findByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })
  expect(document.querySelector('.pcard-price')).toHaveTextContent('12.000.000')
  expect(document.querySelector('.pcard-media img')).toHaveAttribute('src', '/phone.png')
  expect(screen.queryByText('Hết hàng', { exact: true })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thêm vào giỏ hàng' })).toBeEnabled()
  expect(screen.getByText('1 sản phẩm')).toBeInTheDocument()
  expect(screen.getByRole('navigation', { name: 'Đường dẫn trang yêu thích' })).toBeInTheDocument()
  expect(calls).toContainEqual({ path: '/products/p1', method: 'GET', body: null })
})

test('a truly sold-out variant keeps its actual sold-out badge and cannot be added to cart', async () => {
  mockApi({ added: true, productDetail: { ...detail, Variants: [{ ...detail.Variants[0], StockQuantity: 0 }] } })
  show('wishlist-zero-stock', { route: '/yeu-thich' })
  expect(await screen.findByText('Hết hàng', { exact: true })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thêm vào giỏ hàng' })).toBeDisabled()
})

test('unavailable products remain removable and are distinguished from a stock count of zero', async () => {
  mockApi({ added: true, productStatus: 404 }); show('wishlist-unavailable', { route: '/yeu-thich' })
  expect(await screen.findByText('Ngừng bán', { exact: true })).toBeInTheDocument()
  expect(screen.queryByText('Hết hàng', { exact: true })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thêm vào giỏ hàng' })).toBeDisabled()
  await userEvent.setup().click(screen.getByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` }))
  expect(await screen.findByRole('heading', { name: 'Bạn chưa có sản phẩm yêu thích nào.' })).toBeInTheDocument()
})

test('failed product detail loading is retryable and never fabricates a sold-out badge', async () => {
  const { controls } = mockApi({ added: true, productStatus: 503 }); show('wishlist-detail-failure', { route: '/yeu-thich' })
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Không tải được thông tin sản phẩm.')
  expect(screen.queryByText('Hết hàng', { exact: true })).not.toBeInTheDocument()
  controls.productStatus = 200
  await userEvent.setup().click(within(alert).getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' })).toBeEnabled()
})

test('wishlist add-cart uses the single actual variant and updates the existing cart count', async () => {
  const { calls } = mockApi({ added: true }); show('wishlist-cart-single', { route: '/yeu-thich' })
  const changed = vi.fn(); window.addEventListener('vietech-cart-changed', changed)
  try {
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' }))
    expect(await screen.findByText('Đã thêm vào giỏ hàng.')).toBeInTheDocument()
    expect(calls.find((call) => call.path === '/cart/items')).toMatchObject({ method: 'POST', body: { ProductVariantId: 'v1', Quantity: 1 } })
    expect(changed).toHaveBeenCalledOnce()
    expect(screen.queryByRole('heading', { name: 'Chi tiết sản phẩm kiểm thử' })).not.toBeInTheDocument()
  } finally { window.removeEventListener('vietech-cart-changed', changed) }
})

test('multiple variants require a choice before adding; unavailable choices stay disabled', async () => {
  const productDetail = { ...detail, Variants: [...detail.Variants,
    { ...detail.Variants[0], ProductVariantId: 'v2', VariantName: 'Bạc · 512GB', Price: '14000000' },
    { ...detail.Variants[0], ProductVariantId: 'v3', VariantName: 'Xanh · 1TB', Price: '16000000', StockQuantity: 0 }] }
  const { calls } = mockApi({ added: true, productDetail }); show('wishlist-cart-choice', { route: '/yeu-thich' }); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' }))
  const dialog = screen.getByRole('dialog', { name: `Chọn phiên bản ${detail.Name}` })
  expect(calls.some((call) => call.path === '/cart/items')).toBe(false)
  expect(within(dialog).getByRole('option', { name: /Xanh · 1TB/ })).toBeDisabled()
  await user.selectOptions(within(dialog).getByRole('combobox', { name: 'Phiên bản sản phẩm' }), 'v2')
  await user.click(within(dialog).getByRole('button', { name: 'Thêm phiên bản đã chọn vào giỏ' }))
  expect(await screen.findByText('Đã thêm vào giỏ hàng.')).toBeInTheDocument()
  expect(calls.find((call) => call.path === '/cart/items').body).toEqual({ ProductVariantId: 'v2', Quantity: 1 })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('a cart business error stays visible and does not remove the wishlist item', async () => {
  mockApi({ added: true, cartFailure: true }); show('wishlist-cart-failure', { route: '/yeu-thich' })
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Số lượng sản phẩm vượt tồn kho.')
  expect(screen.getByRole('button', { name: `Bỏ ${detail.Name} khỏi yêu thích` })).toHaveAttribute('aria-pressed', 'true')
})

test('a pending wishlist cart request blocks a repeated click', async () => {
  const { calls, releaseCart } = mockApi({ added: true, holdCart: true }); show('wishlist-cart-repeat', { route: '/yeu-thich' })
  const button = await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' })
  fireEvent.click(button); fireEvent.click(button)
  await waitFor(() => expect(calls.filter((call) => call.path === '/cart/items')).toHaveLength(1))
  expect(button).toBeDisabled()
  await act(async () => releaseCart())
  expect(await screen.findByText('Đã thêm vào giỏ hàng.')).toBeInTheDocument()
})
