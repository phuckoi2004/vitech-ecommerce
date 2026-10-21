import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { appRoutes } from '../../routes.jsx'
import { makeAuth } from '../../test/auth.js'

const brands = [{ BrandId: 'apple', Name: 'Apple' }, { BrandId: 'samsung', Name: 'Samsung' }]
const product = index => ({
  ProductId: `p${index}`, Name: `Sản phẩm ${index}`, Slug: `san-pham-${index}`, BrandId: 'apple',
  AverageRating: '0', ReviewCount: 0, SoldQuantity: 0, Images: [],
  Variants: [{ ProductVariantId: `v${index}`, Price: '2000000', OriginalPrice: '2000000', SalePrice: '1500000',
    DiscountPercent: '25', StockQuantity: 3 }],
})
// What GET /products/filters finds: the category chips offer only these.
const searchFilters = {
  Categories: [{ CategoryId: 'phone', Name: 'Điện thoại', Slug: 'dien-thoai', ProductCount: 20 },
    { CategoryId: 'audio', Name: 'Tai nghe', Slug: 'tai-nghe', ProductCount: 5 }],
  Brands: [{ BrandId: 'apple', Name: 'Apple', Slug: 'apple', ProductCount: 25 }],
}
const news = { Items: [
  { NewsArticleId: 'n1', Title: 'Samsung Galaxy S25 có gì mới', Slug: 'galaxy-s25', Summary: null, ThumbnailUrl: null },
  { NewsArticleId: 'n2', Title: 'Chọn tai nghe cho mùa thi', Slug: 'tai-nghe', Summary: 'Gợi ý theo túi tiền.', ThumbnailUrl: null },
], Total: 2, Page: 1, PageSize: 50 }
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

function mockApi(overrides = {}) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async input => {
    const url = new URL(input, 'http://localhost')
    const path = url.pathname.replace(/^\/api/, '')
    calls.push({ path, query: Object.fromEntries(url.searchParams) })
    if (overrides[path]) return overrides[path](url)
    if (path === '/categories') return json([])
    if (path === '/brands') return json(brands)
    if (path === '/brands/slug/apple') return json({ ...brands[0], Slug: 'apple' })
    if (path === '/news') return json(news)
    if (path === '/products') {
      const page = Number(url.searchParams.get('page'))
      const items = Array.from({ length: 25 }, (_, i) => product(i + 1)).slice((page - 1) * 20, page * 20)
      return json({ Items: items, Total: 25, Page: page, PageSize: 20 })
    }
    if (path === '/products/filters') return json(searchFilters)
    if (/^\/products\/p\d+$/.test(path)) return json(product(Number(path.slice('/products/p'.length))))
    return json({ detail: 'Không tìm thấy' }, 404)
  }))
  return calls
}

function renderAt(url) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [url] })
  render(<AuthContext.Provider value={makeAuth()}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
const searches = calls => calls.filter(call => call.path === '/products')
const results = () => screen.getByRole('region', { name: 'Kết quả sản phẩm' })
const names = () => within(results()).queryAllByRole('heading', { level: 3 }).map(el => el.textContent)
const chips = (name) => within(screen.getByRole(name === 'Sắp xếp theo' ? 'region' : 'group', { name })).getAllByRole('button')
afterEach(() => vi.unstubAllGlobals())

test('a search says what it found, sorts by relevance and loads more instead of turning pages', async () => {
  const calls = mockApi()
  renderAt('/tim-kiem?q=samsung%20s25')
  expect(screen.getByRole('heading', { level: 1, name: "Kết quả tìm kiếm cho: 'samsung s25'" })).toBeInTheDocument()
  await waitFor(() => expect(names()).toHaveLength(20))
  expect(screen.getByRole('status')).toHaveTextContent("Tìm thấy 25 sản phẩm cho từ khoá 'samsung s25'")
  expect(document.title).toBe("Kết quả tìm kiếm cho: 'samsung s25' | VieTech")
  expect(chips('Sắp xếp theo').map((chip) => [chip.textContent, chip.getAttribute('aria-pressed')]))
    .toEqual([['Liên quan', 'true'], ['Giá cao', 'false'], ['Giá thấp', 'false']])
  expect(searches(calls)[0].query).toEqual({ keyword: 'samsung s25', page: '1', page_size: '20' })
  expect(results().querySelector('.pcard-price')).toHaveTextContent('1.500.000')
  expect(results().querySelector('.pcard-original del')).toHaveTextContent('2.000.000')
  expect(screen.queryByRole('navigation', { name: 'Phân trang sản phẩm' })).not.toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'Xem thêm 5 sản phẩm' }))
  await waitFor(() => expect(names()).toHaveLength(25))
  expect(names().slice(0, 2)).toEqual(['Sản phẩm 1', 'Sản phẩm 2'])  // earlier products stay
  expect(searches(calls).at(-1).query).toMatchObject({ keyword: 'samsung s25', page: '2' })
  expect(screen.queryByRole('button', { name: /Xem thêm/ })).not.toBeInTheDocument()
}, 15000)  // 25 product cards load one detail each

test('category chips come from what was found and narrow it; sorting keeps the chosen category', async () => {
  const calls = mockApi()
  const router = renderAt('/tim-kiem?q=iphone')
  const user = userEvent.setup()
  await screen.findByRole('group', { name: 'Danh mục' })
  expect(chips('Danh mục').map((chip) => chip.textContent)).toEqual(['Tất cả', 'Điện thoại', 'Tai nghe'])
  expect(calls.find((call) => call.path === '/products/filters').query).toEqual({ keyword: 'iphone' })

  await user.click(screen.getByRole('button', { name: 'Tai nghe' }))
  await waitFor(() => expect(searches(calls).at(-1).query).toMatchObject({ keyword: 'iphone', category_id: 'audio', include_descendants: 'true', page: '1' }))
  expect(screen.getByRole('button', { name: 'Tai nghe' })).toHaveAttribute('aria-pressed', 'true')
  await user.click(screen.getByRole('button', { name: 'Giá thấp' }))
  await waitFor(() => expect(searches(calls).at(-1).query).toMatchObject({ category_id: 'audio', sort: 'price_asc', page: '1' }))
  await user.click(screen.getByRole('button', { name: 'Tất cả' }))
  expect(router.state.location.search).toBe('?q=iphone&sort=price_asc')
  await user.click(screen.getByRole('button', { name: 'Liên quan' }))
  expect(router.state.location.search).toBe('?q=iphone')
  expect(calls.filter((call) => call.path === '/products/filters')).toHaveLength(1)  // chips do not depend on them
})

test('one category found means no category chips', async () => {
  mockApi({ '/products/filters': () => json({ ...searchFilters, Categories: searchFilters.Categories.slice(0, 1) }) })
  renderAt('/tim-kiem?q=pin%20trau')
  await waitFor(() => expect(names()).toHaveLength(20))
  expect(screen.queryByRole('group', { name: 'Danh mục' })).not.toBeInTheDocument()
})

test('related articles mention every searched word, with a link to all news', async () => {
  mockApi()
  renderAt('/tim-kiem?q=galaxy%20samsung')
  const aside = await screen.findByRole('complementary', { name: 'Bài viết liên quan' })
  expect(within(aside).getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
    ['Samsung Galaxy S25 có gì mới', '/tin-tuc/galaxy-s25'], ['Xem tất cả bài viết ›', '/tin-tuc'],
  ])
})

test('submitting the same keyword keeps the chosen category, and a new keyword starts over', async () => {
  const calls = mockApi()
  const router = renderAt('/tim-kiem?q=iphone&category=phone')
  const box = screen.getByRole('searchbox', { name: 'Tìm kiếm sản phẩm' })
  fireEvent.submit(box.closest('form'))
  expect(router.state.location.search).toBe('?q=iphone&category=phone')
  fireEvent.change(box, { target: { value: 'chuot' } })
  fireEvent.submit(box.closest('form'))
  await waitFor(() => expect(searches(calls).at(-1).query).toEqual({ keyword: 'chuot', page: '1', page_size: '20' }))
  expect(router.state.location.search).toBe('?q=chuot')
  expect(box).toHaveValue('chuot')
})

test('empty results give a way to browse again', async () => {
  mockApi({ '/products': url => url.searchParams.get('keyword')
    ? json({ Items: [], Total: 0, Page: 1, PageSize: 20 })
    : json({ Items: [product(1)], Total: 1, Page: 1, PageSize: 20 }) })
  renderAt('/tim-kiem?q=khong-tim-thay')
  expect(await screen.findByRole('heading', { name: 'Không có sản phẩm phù hợp' })).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent("Tìm thấy 0 sản phẩm cho từ khoá 'khong-tim-thay'")
  await userEvent.click(screen.getByRole('link', { name: 'Xem tất cả sản phẩm' }))
  expect(await screen.findByRole('heading', { name: 'Sản phẩm 1' })).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Tìm thấy 1 sản phẩm')
  expect(screen.getByRole('searchbox')).toHaveValue('')
})

test('a failed product request can be retried without losing the search', async () => {
  let failing = true
  const calls = mockApi({ '/products': () => failing ? json({ detail: 'Hệ thống đang bận.' }, 503)
    : json({ Items: [product(1)], Total: 1, Page: 1, PageSize: 20 }) })
  renderAt('/tim-kiem?q=iphone&sort=price_asc')
  expect(await screen.findByRole('alert')).toHaveTextContent('Hệ thống đang bận.')
  expect(screen.queryByRole('heading', { name: 'Không có sản phẩm phù hợp' })).not.toBeInTheDocument()
  failing = false
  await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByRole('heading', { name: 'Sản phẩm 1' })).toBeInTheDocument()
  expect(searches(calls).at(-1).query).toMatchObject({ keyword: 'iphone', sort: 'price_asc' })
})

test('brand pages keep their brand and sort newest first', async () => {
  const calls = mockApi()
  renderAt('/thuong-hieu/apple')
  expect(await screen.findByRole('heading', { level: 1, name: 'Apple' })).toBeInTheDocument()
  await waitFor(() => expect(names()).toHaveLength(20))
  expect(searches(calls).at(-1).query).toMatchObject({ brand_id: 'apple', page: '1' })
  expect(calls.find((call) => call.path === '/products/filters').query).toEqual({ brand_id: 'apple' })
  expect(chips('Sắp xếp theo').map((chip) => chip.textContent)).toEqual(['Mới nhất', 'Giá cao', 'Giá thấp'])
  expect(screen.getByRole('button', { name: 'Mới nhất' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByRole('complementary', { name: 'Bài viết liên quan' })).not.toBeInTheDocument()
})
