// Category page (Figma "Danh sách sản phẩm") with the real catalog API module; `fetch` answers from fixtures.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { appRoutes } from '../../routes.jsx'
import { makeAuth } from '../../test/auth.js'

const category = (id, name, slug, parent = null, extra = {}) => ({
  CategoryId: id, ParentCategoryId: parent, Name: name, Slug: slug, Description: null, DisplayOrder: 0, IsActive: true, ...extra,
})
const CATEGORIES = [
  category('phone', 'Điện thoại', 'dien-thoai', null, { Description: 'Điện thoại chính hãng.\nLọc theo nhu cầu và cấu hình.' }),
  category('gaming', 'Điện thoại chơi game', 'dien-thoai-choi-game', 'phone', { DisplayOrder: 1 }),
  category('battery', 'Điện thoại pin trâu', 'dien-thoai-pin-trau', 'phone', { DisplayOrder: 2 }),
  category('laptop', 'Laptop', 'laptop'),
]
const FILTERS = {
  Brands: [{ BrandId: 'b1', Name: 'Apple', Slug: 'apple', ProductCount: 2 }, { BrandId: 'b2', Name: 'Samsung', Slug: 'samsung', ProductCount: 1 }],
  PriceRanges: [{ Value: '2-4', Label: '2 – 4 triệu', MinPrice: '2000000.00', MaxPrice: '3999999.99', ProductCount: 1 }],
  Facets: [
    { Key: 'chip', Label: 'Chip xử lý', Options: [
      { Value: 'snapdragon', Label: 'Snapdragon', ProductCount: 2 }, { Value: 'apple-a', Label: 'Apple A', ProductCount: 1 }] },
    { Key: 'ram', Label: 'Dung lượng RAM', Options: [{ Value: '8gb', Label: '8 GB', ProductCount: 1 }] },
  ],
}
const product = (index) => ({
  ProductId: `p${index}`, Name: `Máy ${index}`, Slug: `may-${index}`, BrandId: 'b1', CategoryId: 'phone', Status: 'Active',
  AverageRating: '0', ReviewCount: 0, SoldQuantity: 0, Images: [],
  Variants: [{ ProductVariantId: `v${index}`, VariantName: '128GB', Price: '10000000.00', StockQuantity: 2 }],
})

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}

// `total` products split into pages of the requested size; `overrides[path]` replaces an answer.
function mockApi({ total = 25, overrides = {} } = {}) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async (input) => {
    const url = new URL(input, 'http://localhost')
    const path = url.pathname.replace(/^\/api/, '')
    const query = Object.fromEntries(url.searchParams)
    calls.push({ path, query: { ...query, spec: url.searchParams.getAll('spec') } })
    if (path in overrides) return overrides[path](url)
    if (path === '/categories/slug/dien-thoai') return json(CATEGORIES[0])
    if (path === '/categories/slug/dien-thoai-pin-trau') return json(CATEGORIES[2])
    if (path === '/categories') return json(CATEGORIES)
    if (path.endsWith('/filters')) return json(FILTERS)
    if (path === '/products') {
      const page = Number(query.page), size = Number(query.page_size)
      const items = Array.from({ length: total }, (_, index) => product(index + 1)).slice((page - 1) * size, page * size)
      return json({ Items: items, Total: total, Page: page, PageSize: size })
    }
    if (path.startsWith('/products/')) return json(product(Number(path.slice('/products/p'.length))))
    if (path === '/banners') return json([{ BannerId: 'bn1', Title: 'Ưu đãi iPhone', ImageUrl: 'https://cdn.example/b1.png', LinkUrl: '/danh-muc/dien-thoai' }])
    if (path === '/news') return json({ Items: [
      { NewsArticleId: 'n1', Title: 'Cách chọn điện thoại năm 2026', Slug: 'chon-dien-thoai', Summary: 'Theo nhu cầu.', ThumbnailUrl: null },
      { NewsArticleId: 'n2', Title: 'Laptop cho sinh viên', Slug: 'laptop-sinh-vien', Summary: 'Mỏng nhẹ.', ThumbnailUrl: null },
    ], Total: 2, Page: 1, PageSize: 50 })
    if (path === '/pricing/category-offers' || path === '/coupons') return json([])
    return json({ detail: 'Không tìm thấy' }, 404)
  }))
  return calls
}

function renderAt(url) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [url] })
  render(<AuthContext.Provider value={makeAuth()}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

const productCalls = (calls) => calls.filter((call) => call.path === '/products')
const search = (router) => new URLSearchParams(router.state.location.search)

afterEach(() => vi.unstubAllGlobals())

test('shows the design sections from real data and loads 20 popular products first', async () => {
  const calls = mockApi()
  renderAt('/danh-muc/dien-thoai')
  expect(await screen.findByRole('heading', { level: 1, name: 'Điện thoại' })).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Samsung' })).toHaveAttribute('aria-pressed', 'false')
  const needs = screen.getByRole('navigation', { name: 'Nhóm điện thoại' })
  expect(within(needs).getAllByRole('link').map((link) => link.textContent)).toEqual(['Điện thoại chơi game', 'Điện thoại pin trâu'])
  expect(screen.getByRole('button', { name: 'Phổ biến' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('region', { name: 'Thông tin về điện thoại' }).querySelectorAll('p')).toHaveLength(2)
  expect(screen.getByRole('link', { name: 'Ưu đãi iPhone' })).toHaveAttribute('href', '/danh-muc/dien-thoai')
  // The server picks this category's banners.
  expect(calls.find((call) => call.path === '/banners').query.category_id).toBe(CATEGORIES[0].CategoryId)

  const results = screen.getByRole('region', { name: 'Điện thoại nổi bật' })
  await waitFor(() => expect(within(results).getAllByRole('heading', { level: 3 })).toHaveLength(20))
  expect(productCalls(calls)[0].query).toMatchObject({ category_id: 'phone', include_descendants: 'true', sort: 'popular', page: '1', page_size: '20' })

  const news = await screen.findByRole('region', { name: 'Tin tức điện thoại' })
  expect(within(news).getByRole('link', { name: /Cách chọn điện thoại/ })).toHaveAttribute('href', '/tin-tuc/chon-dien-thoai')
  expect(news).not.toHaveTextContent('Laptop cho sinh viên')
})

test('"Xem thêm" appends the next page and disappears when everything is shown', async () => {
  const calls = mockApi()
  renderAt('/danh-muc/dien-thoai')
  await userEvent.click(await screen.findByRole('button', { name: /Xem thêm 5 sản phẩm/ }))
  const results = screen.getByRole('region', { name: 'Điện thoại nổi bật' })
  await waitFor(() => expect(within(results).getAllByRole('heading', { level: 3 })).toHaveLength(25))
  expect(within(results).getByRole('heading', { name: 'Máy 1' })).toBeInTheDocument()
  expect(productCalls(calls).map((call) => call.query.page)).toEqual(['1', '2'])
  expect(screen.queryByRole('button', { name: /Xem thêm/ })).not.toBeInTheDocument()
})

test('returning to a previous filter starts at page 1 after loading more products', async () => {
  const calls = mockApi()
  renderAt('/danh-muc/dien-thoai')
  const user = userEvent.setup()
  const results = await screen.findByRole('region', { name: 'Điện thoại nổi bật' })
  const shown = () => within(results).queryAllByRole('heading', { level: 3 })
  await user.click(await screen.findByRole('button', { name: /Xem thêm 5 sản phẩm/ }))
  await waitFor(() => expect(shown()).toHaveLength(25))

  await user.click(screen.getByRole('button', { name: 'Sẵn hàng' }))
  await waitFor(() => expect(shown()).toHaveLength(20))
  await user.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }))
  await waitFor(() => expect(shown()).toHaveLength(20))
  expect(within(results).getByRole('heading', { name: 'Máy 1' })).toBeInTheDocument()
  expect(productCalls(calls).map((call) => call.query.page)).toEqual(['1', '2', '1', '1'])

  await user.click(screen.getByRole('button', { name: /Xem thêm 5 sản phẩm/ }))
  await waitFor(() => expect(shown()).toHaveLength(25))
})

test('a product hidden between the list and detail does not leave a phantom next page', async () => {
  const calls = mockApi({ overrides: { '/products/p1': () => json({ detail: 'Không tìm thấy sản phẩm' }, 404) } })
  renderAt('/danh-muc/dien-thoai')
  const results = await screen.findByRole('region', { name: 'Điện thoại nổi bật' })
  await waitFor(() => expect(within(results).getAllByRole('heading', { level: 3 })).toHaveLength(19))
  await userEvent.click(screen.getByRole('button', { name: /Xem thêm 5 sản phẩm/ }))
  await waitFor(() => expect(within(results).getAllByRole('heading', { level: 3 })).toHaveLength(24))
  expect(screen.queryByRole('button', { name: /Xem thêm/ })).not.toBeInTheDocument()
  expect(productCalls(calls).map((call) => call.query.page)).toEqual(['1', '2'])
})

test('an empty next page stops loading more even if the total has become stale', async () => {
  const calls = mockApi({ overrides: {
    '/products': (url) => {
      const page = Number(url.searchParams.get('page'))
      const items = page === 1 ? Array.from({ length: 20 }, (_, index) => product(index + 1)) : []
      return json({ Items: items, Total: 25, Page: page, PageSize: 20 })
    },
  } })
  renderAt('/danh-muc/dien-thoai')
  await userEvent.click(await screen.findByRole('button', { name: /Xem thêm 5 sản phẩm/ }))
  await waitFor(() => expect(screen.queryByRole('button', { name: /Xem thêm/ })).not.toBeInTheDocument())
  const results = screen.getByRole('region', { name: 'Điện thoại nổi bật' })
  expect(within(results).getAllByRole('heading', { level: 3 })).toHaveLength(20)
  expect(productCalls(calls).map((call) => call.query.page)).toEqual(['1', '2'])
})

test('criteria panels combine options in the URL and the product query, and close with Escape', async () => {
  const calls = mockApi()
  const router = renderAt('/danh-muc/dien-thoai')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Chip xử lý' }))
  const panel = screen.getByRole('dialog', { name: 'Chip xử lý' })
  await user.click(within(panel).getByRole('button', { name: 'Snapdragon' }))
  await user.click(within(panel).getByRole('button', { name: 'Apple A' }))
  expect(search(router).getAll('spec')).toEqual(['chip:snapdragon', 'chip:apple-a'])
  await waitFor(() => expect(productCalls(calls).at(-1).query).toMatchObject({ spec: ['chip:snapdragon', 'chip:apple-a'], page: '1' }))
  expect(within(panel).getByRole('button', { name: 'Apple A' })).toHaveAttribute('aria-pressed', 'true')
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Chip xử lý \(2\)/ })).toHaveFocus()

  // "Bộ lọc" lists every criterion and opens the chosen one.
  await user.click(screen.getByRole('button', { name: 'Bộ lọc' }))
  await user.click(within(screen.getByRole('dialog', { name: 'Bộ lọc đầy đủ' })).getByRole('button', { name: 'Xem theo giá' }))
  await user.click(within(screen.getByRole('dialog', { name: 'Xem theo giá' })).getByRole('button', { name: '2 – 4 triệu' }))
  await waitFor(() => expect(productCalls(calls).at(-1).query).toMatchObject({ min_price: '2000000.00', max_price: '3999999.99' }))
  await user.click(document.body)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('brand, sort and quick filters update the query; "Xóa bộ lọc" keeps the sort', async () => {
  const calls = mockApi()
  const router = renderAt('/danh-muc/dien-thoai')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Samsung' }))
  await user.click(screen.getByRole('button', { name: 'Giá thấp đến cao' }))
  await user.click(screen.getByRole('button', { name: 'Sẵn hàng' }))
  await user.click(screen.getByRole('button', { name: 'Hàng mới về' }))
  expect(router.state.location.search).toBe('?brand=b2&sort=price_asc&stock=1&new=1')
  await waitFor(() => expect(productCalls(calls).at(-1).query).toMatchObject({
    brand_id: 'b2', sort: 'price_asc', in_stock: 'true', new_arrivals: 'true' }))
  await user.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }))
  expect(router.state.location.search).toBe('?sort=price_asc')
  await user.click(screen.getByRole('button', { name: 'Phổ biến' }))
  expect(router.state.location.search).toBe('')
})

test('an old link drops options the category no longer offers and keeps the homepage price ranges', async () => {
  const calls = mockApi()
  renderAt('/danh-muc/dien-thoai?spec=chip:old&spec=ram:8gb&price=5-10')
  expect(await screen.findByRole('button', { name: 'Dung lượng RAM' })).toHaveClass('is-selected')
  await waitFor(() => expect(productCalls(calls)).toHaveLength(1))
  expect(productCalls(calls)[0].query).toMatchObject({ spec: ['ram:8gb'], min_price: '5000000', max_price: '9999999.99' })
})

test('no match offers to clear the filters', async () => {
  mockApi({ total: 0 })
  renderAt('/danh-muc/dien-thoai?stock=1')
  expect(await screen.findByRole('heading', { name: 'Không có sản phẩm phù hợp' })).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: 'Xóa bộ lọc' })).toHaveLength(2)
  expect(screen.queryByRole('button', { name: /Xem thêm/ })).not.toBeInTheDocument()
})

test('a failed next page keeps the products already shown and can be retried', async () => {
  let failures = 1
  const calls = mockApi({ overrides: {
    '/products': (url) => {
      const page = Number(url.searchParams.get('page'))
      if (page === 2 && failures-- > 0) return json({ detail: 'Máy chủ bận' }, 503)
      const items = Array.from({ length: 25 }, (_, index) => product(index + 1)).slice((page - 1) * 20, page * 20)
      return json({ Items: items, Total: 25, Page: page, PageSize: 20 })
    },
  } })
  renderAt('/danh-muc/dien-thoai')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /Xem thêm 5 sản phẩm/ }))
  expect(await screen.findByText('Máy chủ bận')).toBeInTheDocument()
  const results = screen.getByRole('region', { name: 'Điện thoại nổi bật' })
  expect(within(results).getAllByRole('heading', { level: 3 })).toHaveLength(20)
  await user.click(screen.getByRole('button', { name: 'Thử lại' }))
  await waitFor(() => expect(within(results).getAllByRole('heading', { level: 3 })).toHaveLength(25))
  expect(productCalls(calls).map((call) => call.query.page)).toEqual(['1', '2', '2'])
})
