// Home page with the real catalog API module; `fetch` answers from fixtures by URL.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { appRoutes } from '../../routes.jsx'
import { makeAuth } from '../../test/auth.js'

const category = (id, name, slug, parent = null) => ({
  CategoryId: id, ParentCategoryId: parent, Name: name, Slug: slug, Description: null, DisplayOrder: 0, IsActive: true,
})

const ROOTS = [category('c-phone', 'Điện thoại', 'dien-thoai'), category('c-laptop', 'Laptop', 'laptop'), category('c-audio', 'Tai nghe', 'tai-nghe')]
const CHILDREN = { 'c-phone': [category('c-gaming', 'Điện thoại chơi game', 'dien-thoai-choi-game', 'c-phone')] }
const BRANDS = [
  { BrandId: 'b-apple', Name: 'Apple', Slug: 'apple', Description: null, LogoUrl: null, IsActive: true },
  { BrandId: 'b-samsung', Name: 'Samsung', Slug: 'samsung', Description: null, LogoUrl: 'https://cdn.example/samsung.png', IsActive: true },
]

const DETAILS = {
  p1: {
    ProductId: 'p1', CategoryId: 'c-phone', BrandId: 'b-apple', Name: 'iPhone 18 Pro Max', Slug: 'iphone-18-pro-max', Status: 'Active',
    AverageRating: '4.80', ReviewCount: 12, SoldQuantity: 1250,
    Variants: [{ Price: '24990000.00', StockQuantity: 0 }, { Price: '20990000.00', StockQuantity: 3 }],
    Images: [{ ImageUrl: 'https://cdn.example/p1.png', DisplayOrder: 0, IsDefault: true }],
  },
  p2: {
    ProductId: 'p2', CategoryId: 'c-gaming', BrandId: 'b-samsung', Name: 'Galaxy S26 Ultra', Slug: 'galaxy-s26-ultra', Status: 'Active',
    AverageRating: '0.00', ReviewCount: 0, SoldQuantity: 0,
    Variants: [{ Price: '31490000.00', StockQuantity: 0 }],
    Images: [],
  },
}

const PRODUCTS_BY_CATEGORY = { '': ['p1', 'p2'], 'c-phone': ['p1'], 'c-gaming': ['p2'], 'c-laptop': [], 'c-audio': [] }

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}

// `overrides[path]` replaces the fixture answer for that path (a function receives the URL).
function mockApi(overrides = {}) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async (input) => {
    const url = new URL(input, 'http://localhost')
    const path = url.pathname.replace(/^\/api/, '')
    calls.push(`${path}${url.search}`)
    if (path in overrides) return typeof overrides[path] === 'function' ? overrides[path](url) : overrides[path]
    if (path === '/categories') {
      const parent = url.searchParams.get('parent_id')
      return json(parent ? CHILDREN[parent] ?? [] : ROOTS)
    }
    if (path === '/brands') return json(BRANDS)
    if (path === '/pricing/category-offers') return json(ROOTS.map((item) => ({
      CategoryId: item.CategoryId, AvailableProductCount: item.CategoryId === 'c-phone' ? 1 : 0,
      MaxDiscountAmount: '0', MaxDiscountPercent: '0',
    })))
    if (path === '/payment-methods' || path === '/shipping-methods') return json([])
    if (path === '/banners') return json([])
    if (path === '/news') return json({ Items: [{ NewsArticleId: 'n1', Title: 'Chọn điện thoại năm 2026', Slug: 'chon-dien-thoai', Summary: 'Gợi ý theo nhu cầu.', ThumbnailUrl: null, Status: 'Published', PublishedAt: null }], Total: 1, Page: 1, PageSize: 3 })
    if (path === '/products') {
      const categoryId = url.searchParams.get('category_id') ?? ''
      let ids = [...(PRODUCTS_BY_CATEGORY[categoryId] ?? [])]
      if (url.searchParams.get('include_descendants') === 'true') {
        for (const child of CHILDREN[categoryId] ?? []) ids.push(...(PRODUCTS_BY_CATEGORY[child.CategoryId] ?? []))
      }
      const brand = url.searchParams.get('brand_id')
      if (brand) ids = ids.filter((id) => DETAILS[id].BrandId === brand)
      ids = ids.filter((id) => {
        const price = Math.min(...DETAILS[id].Variants.map((variant) => Number(variant.Price)))
        return (!url.searchParams.has('min_price') || price >= Number(url.searchParams.get('min_price')))
          && (!url.searchParams.has('max_price') || price <= Number(url.searchParams.get('max_price')))
      })
      const size = Number(url.searchParams.get('page_size'))
      return json({ Items: ids.slice(0, size).map((id) => ({ ProductId: id, BrandId: DETAILS[id].BrandId,
        CategoryId: DETAILS[id].CategoryId, SoldQuantity: DETAILS[id].SoldQuantity })), Total: ids.length, Page: 1, PageSize: size })
    }
    const product = /^\/products\/(\w+)$/.exec(path)
    if (product && DETAILS[product[1]]) return json(DETAILS[product[1]])
    if (path === '/users/me/notifications/unread-count') return json({ Count: 3 })
    return json({ detail: 'Không tìm thấy' }, 404)
  }))
  return calls
}

function renderHome(auth = makeAuth()) {
  const router = createMemoryRouter(appRoutes, { initialEntries: ['/'] })
  render(<AuthContext.Provider value={auth}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

function endBannerTransition(carousel, target = carousel.querySelector('.home-banner-track'), propertyName = 'transform') {
  const event = new Event('transitionend', { bubbles: true })
  Object.defineProperty(event, 'propertyName', { value: propertyName })
  fireEvent(target, event)
}

async function settleBanner(carousel) {
  endBannerTransition(carousel)
  await waitFor(() => expect(carousel).toHaveAttribute('aria-busy', 'false'))
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('catalog sections', () => {
  test('signed-in customers can add a home product to their wishlist from its heart button', async () => {
    const calls = mockApi({
      '/wishlist/items': () => json({ WishlistItemId: 'w1' }, 201),
      '/wishlist/products/p1': () => new Response(null, { status: 204 }),
    })
    renderHome(makeAuth({ role: 'Customer' }))
    const user = userEvent.setup()
    const heart = await screen.findByRole('button', { name: `Thêm ${DETAILS.p1.Name} vào yêu thích` })
    await user.click(heart)
    expect(heart).toHaveAttribute('aria-pressed', 'true')
    expect(calls).toContain('/wishlist/items')
    expect(heart).toHaveAccessibleName(`Bỏ ${DETAILS.p1.Name} khỏi yêu thích`)
    await user.click(heart)
    expect(heart).toHaveAttribute('aria-pressed', 'false')
    expect(calls).toContain('/wishlist/products/p1')
  })

  test('guest heart buttons ask for sign-in or registration and do not call wishlist API', async () => {
    const calls = mockApi()
    const router = renderHome()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: `Thêm ${DETAILS.p1.Name} vào yêu thích` }))
    expect(await screen.findByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })).toBeInTheDocument()
    expect(calls).not.toContain('/wishlist/items')
    await user.click(screen.getByRole('link', { name: 'Đăng nhập' }))
    expect(router.state.location.pathname).toBe('/dang-nhap')
    expect(router.state.location.search).toBe('?next=%2Fsan-pham%2Fiphone-18-pro-max')
  })

  test('categories, newest products, shortcuts, news and brands come from the API', async () => {
    const calls = mockApi()
    renderHome()

    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    expect(await within(menu).findByRole('link', { name: 'Điện thoại', exact: true })).toHaveAttribute('href', '/danh-muc/dien-thoai')

    const newest = screen.getByRole('region', { name: 'Sản phẩm nổi bật' })
    const iphone = (await within(newest).findByRole('heading', { name: 'iPhone 18 Pro Max' })).closest('a')
    expect(iphone).toHaveAttribute('href', '/san-pham/iphone-18-pro-max')
    expect(iphone).toHaveTextContent('20.990.000 ₫')
    expect(iphone).not.toHaveTextContent('Từ')
    expect(iphone).toHaveTextContent('4,8')
    expect(iphone).toHaveTextContent('Đã bán 1,2k')
    const galaxy = within(newest).getByRole('heading', { name: 'Galaxy S26 Ultra' }).closest('a')
    expect(galaxy).toHaveTextContent('Hết hàng')
    expect(galaxy).toHaveTextContent('31.490.000 ₫')
    expect(galaxy).not.toHaveTextContent('Từ')

    const shortcuts = screen.getByRole('region', { name: 'Mua sắm theo danh mục' })
    expect(await within(shortcuts).findByText('Khám phá sản phẩm')).toBeInTheDocument()
    expect(within(shortcuts).getAllByText('Sắp có hàng')).toHaveLength(2)
    expect(within(shortcuts).getByRole('link', { name: 'Mua ngay: Laptop' })).toHaveAttribute('href', '/danh-muc/laptop')

    expect(await screen.findByRole('link', { name: /Chọn điện thoại năm 2026/ })).toHaveAttribute('href', '/tin-tuc/chon-dien-thoai')
    // The 10 latest articles in a scrolling row, and a way to all of them.
    expect(calls.filter((call) => call.startsWith('/news'))).toEqual(['/news?page=1&page_size=10'])
    expect(screen.getByRole('link', { name: 'Xem tất cả tin tức' })).toHaveAttribute('href', '/tin-tuc')
    // Coupons are offered where they are applied, in the cart; the home page does not list them.
    expect(screen.queryByRole('region', { name: 'Mã ưu đãi công khai' })).not.toBeInTheDocument()
    expect(calls.some((call) => call.startsWith('/coupons'))).toBe(false)
    const brands = screen.getByRole('region', { name: 'Thương hiệu nổi bật' })
    expect(within(brands).getByRole('link', { name: 'Samsung' })).toHaveAttribute('href', '/thuong-hieu/samsung')

    // Empty banner data keeps the area without displaying sample product images.
    const hero = screen.getByRole('region', { name: 'Danh mục và chương trình nổi bật' })
    expect(within(hero).getByRole('status')).toHaveTextContent('Chưa có chương trình nổi bật.')
    expect(document.body).not.toHaveTextContent(/Giảm \d+%|Trả góp/)
    expect(screen.queryByRole('heading', { name: 'Tư vấn mua hàng', exact: true })).not.toBeInTheDocument()
  })

  test('category promos use real automatic offer maxima and keep valid category links', async () => {
    const calls = mockApi({ '/pricing/category-offers': json([
      { CategoryId: 'c-phone', AvailableProductCount: 2, MaxDiscountAmount: '2000000', MaxDiscountPercent: '12.82' },
      { CategoryId: 'c-laptop', AvailableProductCount: 3, MaxDiscountAmount: '2000000', MaxDiscountPercent: '6.45' },
      { CategoryId: 'c-audio', AvailableProductCount: 1, MaxDiscountAmount: '100000', MaxDiscountPercent: '10' },
    ]) })
    renderHome()
    const promos = await screen.findByRole('region', { name: 'Mua sắm theo danh mục' })
    expect(await within(promos).findByText('Giảm đến 13%')).toBeInTheDocument()
    expect(within(promos).getByText('Ưu đãi đến 2 TRIỆU')).toBeInTheDocument()
    expect(within(promos).getByText('Giảm đến 10%')).toBeInTheDocument()
    expect(within(promos).getByRole('link', { name: 'Mua ngay: Tai nghe' })).toHaveAttribute('href', '/danh-muc/tai-nghe')
    expect(promos).not.toHaveTextContent(/30%|50%|5 TRIỆU|sản phẩm$/)
    expect(calls.filter((path) => path === '/pricing/category-offers')).toHaveLength(1)
  })

  test('every root category gets a shortcut card, beyond the four that fit across', async () => {
    const roots = [...ROOTS, category('c-tablet', 'Máy tính bảng', 'may-tinh-bang'), category('c-keyboard', 'Bàn phím', 'ban-phim')]
    mockApi({ '/categories': (url) => json(url.searchParams.has('parent_id') ? [] : roots) })
    renderHome()
    const promos = await screen.findByRole('region', { name: 'Mua sắm theo danh mục' })
    expect(within(promos).getAllByRole('link').map((link) => link.getAttribute('aria-label'))).toEqual([
      'Mua ngay: Điện thoại', 'Mua ngay: Laptop', 'Mua ngay: Tai nghe', 'Mua ngay: Máy tính bảng', 'Mua ngay: Bàn phím'])
    expect(within(promos).getByRole('link', { name: 'Mua ngay: Bàn phím' })).toHaveAttribute('href', '/danh-muc/ban-phim')
  })

  test('offer failure leaves usable category links without advertising a sample discount', async () => {
    mockApi({ '/pricing/category-offers': json({ detail: 'Tạm thời không thể tải ưu đãi' }, 503) })
    renderHome()
    const promos = await screen.findByRole('region', { name: 'Mua sắm theo danh mục' })
    await waitFor(() => expect(within(promos).getAllByText('Khám phá sản phẩm')).toHaveLength(3))
    expect(within(promos).getByRole('link', { name: 'Mua ngay: Laptop' })).toHaveAttribute('href', '/danh-muc/laptop')
    expect(promos).not.toHaveTextContent(/Giảm đến|Ưu đãi đến/)
  })

  test('tabs switch categories; sub-category and brand chips open their product lists right away', async () => {
    const calls = mockApi({ '/categories/slug/dien-thoai-choi-game': () => json(CHILDREN['c-phone'][0]) })
    const user = userEvent.setup()
    const router = renderHome()

    const showcase = await screen.findByRole('region', { name: 'Điện thoại, Laptop' })
    const panel = within(showcase).getByRole('tabpanel')
    expect(await within(panel).findByRole('heading', { name: 'Galaxy S26 Ultra' })).toBeInTheDocument()
    expect(within(panel).getByRole('heading', { name: 'iPhone 18 Pro Max' })).toBeInTheDocument()
    expect(calls).toContain('/products?category_id=c-phone&include_descendants=true&page=1&page_size=10')
    expect(await within(panel).findByRole('link', { name: 'Apple' })).toHaveAttribute('href', '/danh-muc/dien-thoai?brand=b-apple')
    expect(within(panel).getByRole('link', { name: 'Điện thoại chơi game' })).toHaveAttribute('href', '/danh-muc/dien-thoai-choi-game')
    expect(within(panel).getByRole('link', { name: /Xem tất cả/ })).toHaveAttribute('href', '/danh-muc/dien-thoai')

    await user.click(within(showcase).getByRole('tab', { name: 'Laptop' }))
    expect(within(showcase).getByRole('tab', { name: 'Laptop' })).toHaveAttribute('aria-selected', 'true')
    expect(await within(showcase).findByRole('heading', { name: 'Chưa có sản phẩm' })).toBeInTheDocument()

    // A single remaining root category gets a heading instead of tabs.
    expect(screen.getByRole('heading', { level: 2, name: 'Tai nghe' })).toBeInTheDocument()

    await user.click(within(showcase).getByRole('tab', { name: 'Điện thoại' }))
    await user.click(await within(within(showcase).getByRole('tabpanel')).findByRole('link', { name: 'Điện thoại chơi game' }))
    expect(router.state.location.pathname).toBe('/danh-muc/dien-thoai-choi-game')
  })

  test('banners are shown as a carousel with their links', async () => {
    mockApi({
      '/banners': json([
        { BannerId: 'bn1', Title: 'Ra mắt iPhone 18', ImageUrl: 'https://cdn.example/bn1.png', LinkUrl: '/danh-muc/dien-thoai', DisplayOrder: 0 },
        { BannerId: 'bn2', Title: 'Laptop cho sinh viên', ImageUrl: 'https://cdn.example/bn2.png', LinkUrl: 'https://vietech.example/laptop', DisplayOrder: 1 },
      ]),
    })
    const user = userEvent.setup()
    renderHome()

    const carousel = await screen.findByRole('region', { name: 'Chương trình nổi bật' })
    expect(within(carousel).getByRole('link', { name: 'Ra mắt iPhone 18' })).toHaveAttribute('href', '/danh-muc/dien-thoai')
    expect(within(carousel).getByRole('button', { name: 'Xem banner 1' })).toHaveAttribute('aria-current', 'true')
    await user.hover(carousel)
    await user.click(within(carousel).getByRole('button', { name: 'Banner tiếp theo' }))
    expect(within(carousel).getByRole('button', { name: 'Xem banner 2' })).toHaveAttribute('aria-current', 'true')
    expect(within(carousel).getByRole('link', { name: 'Laptop cho sinh viên' })).toHaveAttribute('href', 'https://vietech.example/laptop')
    await settleBanner(carousel)
    await user.click(within(carousel).getByRole('button', { name: 'Banner tiếp theo' }))
    expect(within(carousel).getByRole('button', { name: 'Xem banner 1' })).toHaveAttribute('aria-current', 'true')
    await settleBanner(carousel)
    await user.click(within(carousel).getByRole('button', { name: 'Banner trước' }))
    expect(within(carousel).getByRole('button', { name: 'Xem banner 2' })).toHaveAttribute('aria-current', 'true')
    await settleBanner(carousel)
    await user.click(within(carousel).getByRole('button', { name: 'Xem banner 1' }))
    expect(within(carousel).getByRole('link', { name: 'Ra mắt iPhone 18' })).toBeInTheDocument()
    expect(within(carousel).queryByRole('link', { name: 'Laptop cho sinh viên' })).not.toBeInTheDocument()
    await settleBanner(carousel)

    // Ignore further clicks until both the transition and any loop rebase have finished.
    const next = within(carousel).getByRole('button', { name: 'Banner tiếp theo' })
    act(() => {
      fireEvent.click(next)
      fireEvent.click(next)
    })
    expect(within(carousel).getByRole('button', { name: 'Xem banner 2' })).toHaveAttribute('aria-current', 'true')
    expect(next).toHaveAttribute('aria-disabled', 'true')
    await settleBanner(carousel)
    expect(next).toHaveAttribute('aria-disabled', 'false')
  })

  test('the persistent track slides through both loop clones and rebases without a transition', async () => {
    mockApi({ '/banners': json([1, 2, 3].map((id) => ({ BannerId: `bn${id}`, Title: `Banner ${id}`, ImageUrl: `https://cdn.example/${id}.png` }))) })
    renderHome()
    const carousel = await screen.findByRole('region', { name: 'Chương trình nổi bật' })
    fireEvent.mouseEnter(carousel)
    const track = carousel.querySelector('.home-banner-track')
    const slides = [...track.children]
    const next = within(carousel).getByRole('button', { name: 'Banner tiếp theo' })
    const prev = within(carousel).getByRole('button', { name: 'Banner trước' })
    expect(slides).toHaveLength(5)
    expect(track.style.transform).toBe('translate3d(-100%, 0, 0)')
    expect(slides[0]).toHaveAttribute('inert')
    expect(slides[4]).toHaveAttribute('aria-hidden', 'true')

    fireEvent.click(prev)
    expect(track.style.transform).toBe('translate3d(-0%, 0, 0)')
    expect(carousel).toHaveAttribute('aria-busy', 'true')
    endBannerTransition(carousel, slides[1])
    endBannerTransition(carousel, track, 'opacity')
    expect(carousel).toHaveAttribute('aria-busy', 'true')
    endBannerTransition(carousel)
    expect(track).toHaveClass('is-resetting')
    expect(track.style.transform).toBe('translate3d(-300%, 0, 0)')
    fireEvent.click(next)
    expect(track.style.transform).toBe('translate3d(-300%, 0, 0)')
    await waitFor(() => expect(carousel).toHaveAttribute('aria-busy', 'false'))

    fireEvent.click(next)
    expect(track.style.transform).toBe('translate3d(-400%, 0, 0)')
    endBannerTransition(carousel)
    expect(track).toHaveClass('is-resetting')
    expect(track.style.transform).toBe('translate3d(-100%, 0, 0)')
    await waitFor(() => expect(carousel).toHaveAttribute('aria-busy', 'false'))
    expect([...track.children]).toEqual(slides)

    fireEvent.click(within(carousel).getByRole('button', { name: 'Xem banner 3' }))
    expect(track.style.transform).toBe('translate3d(-300%, 0, 0)')
    await settleBanner(carousel)
  })

  test('reduced motion is read from matchMedia and changes during a transition release navigation', async () => {
    let listener
    const media = { matches: false, addEventListener: vi.fn((_, fn) => { listener = fn }), removeEventListener: vi.fn() }
    vi.stubGlobal('matchMedia', vi.fn(() => media))
    mockApi({ '/banners': json([1, 2].map((id) => ({ BannerId: `bn${id}`, Title: `Banner ${id}`, ImageUrl: `https://cdn.example/${id}.png` }))) })
    renderHome()
    const carousel = await screen.findByRole('region', { name: 'Chương trình nổi bật' })
    const next = within(carousel).getByRole('button', { name: 'Banner tiếp theo' })
    fireEvent.click(next)
    expect(carousel).toHaveAttribute('aria-busy', 'true')
    act(() => { media.matches = true; listener() })
    expect(carousel).toHaveAttribute('aria-busy', 'false')
    fireEvent.click(next)
    expect(carousel).toHaveAttribute('aria-busy', 'false')
    expect(carousel.querySelector('.home-banner-track').style.transform).toBe('translate3d(-100%, 0, 0)')
    expect(window.matchMedia).toHaveBeenCalledWith('(prefers-reduced-motion: reduce)')
    act(() => { media.matches = false; listener() })
    fireEvent.click(next)
    expect(carousel).toHaveAttribute('aria-busy', 'true')
    await settleBanner(carousel)
  })

  test('autoplay pauses on hover and a missing transitionend cannot leave the carousel locked', async () => {
    mockApi({ '/banners': json([1, 2].map((id) => ({ BannerId: `bn${id}`, Title: `Banner ${id}`, ImageUrl: `https://cdn.example/${id}.png` }))) })
    renderHome()
    const carousel = await screen.findByRole('region', { name: 'Chương trình nổi bật' })
    fireEvent.mouseEnter(carousel)
    vi.useFakeTimers()
    act(() => vi.advanceTimersByTime(6000))
    expect(within(carousel).getByRole('button', { name: 'Xem banner 1' })).toHaveAttribute('aria-current', 'true')
    fireEvent.mouseLeave(carousel)
    act(() => vi.advanceTimersByTime(5000))
    expect(within(carousel).getByRole('button', { name: 'Xem banner 2' })).toHaveAttribute('aria-current', 'true')
    expect(carousel).toHaveAttribute('aria-busy', 'true')
    act(() => vi.advanceTimersByTime(900))
    expect(carousel).toHaveAttribute('aria-busy', 'false')
  })

  test('an empty banner list does not invent phone images or product links', async () => {
    mockApi()
    renderHome()

    const hero = screen.getByRole('region', { name: 'Danh mục và chương trình nổi bật' })
    expect(await within(hero).findByText('Chưa có chương trình nổi bật.')).toBeInTheDocument()
    expect(within(hero).queryAllByRole('img')).toHaveLength(0)
    expect(within(hero).queryByRole('region', { name: 'Chương trình nổi bật' })).not.toBeInTheDocument()
    expect(within(hero).queryByRole('button', { name: 'Banner tiếp theo' })).not.toBeInTheDocument()
    expect(hero.querySelector('a[href^="/san-pham/"]')).toBeNull()
  })

  test('a failed banner request shows an error and retry loads only the API banner', async () => {
    let failing = true
    mockApi({ '/banners': () => failing ? json({ detail: 'Không thể tải banner lúc này.' }, 503)
      : json([{ BannerId: 'admin-banner', Title: 'Banner do Admin quản lý', ImageUrl: 'https://cdn.example/admin-banner.png', LinkUrl: '/san-pham/mau-do-admin-tao' }]) })
    const user = userEvent.setup()
    renderHome()

    const hero = screen.getByRole('region', { name: 'Danh mục và chương trình nổi bật' })
    expect(await within(hero).findByRole('heading', { name: 'Không tải được banner' })).toBeInTheDocument()
    expect(within(hero).queryAllByRole('img')).toHaveLength(0)
    expect(within(hero).queryByText('Chưa có chương trình nổi bật.')).not.toBeInTheDocument()
    failing = false
    await user.click(within(hero).getByRole('button', { name: 'Thử lại' }))
    const image = await within(hero).findByRole('img', { name: 'Banner do Admin quản lý' })
    expect(image).toHaveAttribute('src', 'https://cdn.example/admin-banner.png')
    expect(image.closest('a')).toHaveAttribute('href', '/san-pham/mau-do-admin-tao')
    expect(within(hero).queryByRole('button', { name: 'Banner tiếp theo' })).not.toBeInTheDocument()
  })

  test('a failed product list can be retried', async () => {
    let failing = true
    mockApi({
      '/products': (url) => {
        if (failing && !url.searchParams.has('category_id')) return json({ detail: 'Hệ thống đang bận.' }, 503)
        return json({ Items: [{ ProductId: 'p1' }], Total: 1, Page: 1, PageSize: 5 })
      },
    })
    const user = userEvent.setup()
    renderHome()

    const newest = screen.getByRole('region', { name: 'Sản phẩm nổi bật' })
    expect(await within(newest).findByRole('heading', { name: 'Không tải được sản phẩm' })).toBeInTheDocument()
    failing = false
    await user.click(within(newest).getByRole('button', { name: 'Thử lại' }))
    expect(await within(newest).findByRole('heading', { name: 'iPhone 18 Pro Max' })).toBeInTheDocument()
  })
})

describe('category menu beside the banner', () => {
  test('category images come from the API and fall back to icons if missing or broken', async () => {
    mockApi({ '/categories': (url) => json(url.searchParams.get('parent_id')
      ? [{ ...CHILDREN['c-phone'][0], ImageUrl: 'https://cdn.example/child.png' }]
      : ROOTS.map((item, index) => ({ ...item, ImageUrl: index === 0 ? 'https://cdn.example/phone.png' : null }))) })
    renderHome()
    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    const button = await within(menu).findByRole('link', { name: 'Điện thoại', exact: true })
    expect(button.querySelector('img')).toHaveAttribute('src', 'https://cdn.example/phone.png')
    fireEvent.error(button.querySelector('img'))
    expect(button.querySelector('svg')).toBeInTheDocument()
    expect(within(menu).getByRole('link', { name: 'Laptop', exact: true }).querySelector('svg')).toBeInTheDocument()
  })

  test('brand and price filters keep category scope, without child categories or suggestions', async () => {
    const calls = mockApi({
      '/brands': () => json([...BRANDS, { BrandId: 'b-unrelated', Name: 'Hãng chỉ bán laptop', Slug: 'laptop-brand' }]),
      '/categories/slug/dien-thoai': json(ROOTS[0]),
    })
    const user = userEvent.setup()
    const router = renderHome()
    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    const phone = await within(menu).findByRole('link', { name: 'Điện thoại', exact: true })
    fireEvent.keyDown(phone, { key: 'ArrowRight' })
    const panel = await within(menu).findByRole('region', { name: 'Khám phá Điện thoại' })
    expect(phone).toHaveAttribute('aria-expanded', 'true')
    expect(await within(panel).findByRole('link', { name: 'Apple', exact: true })).toHaveAttribute('href', '/danh-muc/dien-thoai?brand=b-apple')
    expect(await within(panel).findByRole('link', { name: 'Samsung', exact: true })).toHaveAttribute('href', '/danh-muc/dien-thoai?brand=b-samsung')
    const samsung = within(panel).getByRole('link', { name: 'Samsung', exact: true })
    expect(samsung.querySelector('img')).toHaveAttribute('src', BRANDS[1].LogoUrl)
    fireEvent.error(samsung.querySelector('img'))
    expect(samsung).toHaveTextContent('Samsung')
    expect(within(panel).queryByRole('link', { name: 'Hãng chỉ bán laptop' })).not.toBeInTheDocument()
    expect(within(panel).queryByRole('region', { name: 'Danh mục con' })).not.toBeInTheDocument()
    expect(within(panel).queryByRole('region', { name: 'Gợi ý sản phẩm' })).not.toBeInTheDocument()
    expect(within(panel).queryByRole('link', { name: 'Xem tất cả' })).not.toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: 'Dưới 5 triệu' })).toHaveAttribute('href', '/danh-muc/dien-thoai?price=under-5')
    expect(within(panel).getByRole('link', { name: 'Từ 20 triệu' })).toHaveAttribute('href', '/danh-muc/dien-thoai?price=from-20')
    expect(within(panel).getByRole('region', { name: 'Thương hiệu' }).querySelectorAll('a')).toHaveLength(2)
    await user.click(within(panel).getByRole('link', { name: 'Apple', exact: true }))
    expect(router.state.location.pathname).toBe('/danh-muc/dien-thoai')
    expect(router.state.location.search).toBe('?brand=b-apple')
    await waitFor(() => expect(calls.some((call) => call.startsWith('/products?') && call.includes('category_id=c-phone') && call.includes('brand_id=b-apple'))).toBe(true))
  })

  test('switching to an empty category removes previous brands', async () => {
    mockApi()
    renderHome()
    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    fireEvent.keyDown(await within(menu).findByRole('link', { name: 'Điện thoại', exact: true }), { key: 'ArrowRight' })
    const phone = await within(menu).findByRole('region', { name: 'Khám phá Điện thoại' })
    await within(phone).findByRole('link', { name: 'Apple', exact: true })
    fireEvent.keyDown(within(menu).getByRole('link', { name: 'Laptop', exact: true }), { key: 'ArrowRight' })
    const laptop = await within(menu).findByRole('region', { name: 'Khám phá Laptop' })
    await within(laptop).findByText('Chưa có thương hiệu có sản phẩm trong danh mục này.')
    expect(within(laptop).queryByRole('link', { name: 'Apple', exact: true })).not.toBeInTheDocument()
    expect(within(laptop).getAllByRole('link')).toHaveLength(5)
  })

  test('choosing a menu price range applies it to all category results', async () => {
    const calls = mockApi({ '/categories/slug/dien-thoai': () => json(ROOTS[0]) })
    const router = renderHome()
    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    fireEvent.keyDown(await within(menu).findByRole('link', { name: 'Điện thoại', exact: true }), { key: 'ArrowRight' })
    fireEvent.click(within(menu).getByRole('link', { name: 'Dưới 5 triệu' }))
    await screen.findByText('Không có sản phẩm phù hợp')
    expect(router.state.location.pathname).toBe('/danh-muc/dien-thoai')
    // The menu's range is not one of the category's own, yet it stays chosen and removable on the category page.
    fireEvent.click(screen.getByRole('button', { name: 'Xem theo giá' }))
    expect(within(screen.getByRole('dialog', { name: 'Xem theo giá' })).getByRole('button', { name: 'Dưới 5 triệu' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(calls.some((call) => call.startsWith('/products?') && call.includes('category_id=c-phone') && call.includes('max_price=4999999.99'))).toBe(true)
  })

  test('keyboard opens and closes the panel with focus restored, and outside clicks dismiss it', async () => {
    mockApi()
    renderHome()
    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    const button = await within(menu).findByRole('link', { name: 'Điện thoại', exact: true })
    button.focus()
    fireEvent.keyDown(button, { key: 'ArrowRight' })
    const panel = await within(menu).findByRole('region', { name: 'Khám phá Điện thoại' })
    expect(within(panel).getByRole('button', { name: 'Đóng danh mục' })).toHaveFocus()
    fireEvent.keyDown(document.activeElement, { key: 'Escape' })
    expect(within(menu).queryByRole('region', { name: 'Khám phá Điện thoại' })).not.toBeInTheDocument()
    expect(button).toHaveFocus()
    fireEvent.keyDown(button, { key: 'ArrowRight' })
    expect(button).toHaveAttribute('aria-expanded', 'true')
    fireEvent.pointerDown(document.body)
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  test('desktop hover opens the panel; the close button dismisses it', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }))
    mockApi()
    renderHome()
    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    const button = await within(menu).findByRole('link', { name: 'Điện thoại', exact: true })
    fireEvent.mouseEnter(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(within(menu).getByRole('button', { name: 'Đóng danh mục' }))
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  test.each([
    ['Điện thoại', '/danh-muc/dien-thoai', 'c-phone'],
    ['Laptop', '/danh-muc/laptop', 'c-laptop'],
  ])('clicking %s opens its product list', async (name, path, categoryId) => {
    const calls = mockApi({ [`/categories/slug/${path.split('/').at(-1)}`]: () => json(ROOTS.find((item) => item.CategoryId === categoryId)) })
    const router = renderHome()
    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    await userEvent.click(await within(menu).findByRole('link', { name, exact: true }))
    expect(router.state.location.pathname).toBe(path)
    expect(await screen.findByRole('heading', { level: 1, name })).toBeInTheDocument()
    await waitFor(() => expect(calls.some((call) => call.startsWith('/products?') && call.includes(`category_id=${categoryId}`))).toBe(true))
  })

  test('failed brand data is retryable rather than shown as an empty category', async () => {
    let failing = true
    mockApi({ '/products': (url) => url.searchParams.get('page_size') === '100' && failing
      ? json({ detail: 'Không tải được hãng.' }, 503)
      : json({ Items: [{ ProductId: 'p1', BrandId: 'b-apple' }], Total: 1, Page: 1, PageSize: 100 }) })
    renderHome()
    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    fireEvent.keyDown(await within(menu).findByRole('link', { name: 'Điện thoại', exact: true }), { key: 'ArrowRight' })
    const panel = await within(menu).findByRole('region', { name: 'Khám phá Điện thoại' })
    const brands = within(panel).getByRole('region', { name: 'Thương hiệu' })
    await within(brands).findByText('Không tải được hãng.')
    expect(within(brands).queryByText('Chưa có thương hiệu có sản phẩm trong danh mục này.')).not.toBeInTheDocument()
    failing = false
    fireEvent.click(within(brands).getByRole('button', { name: 'Thử lại' }))
    expect(await within(brands).findByRole('link', { name: 'Apple' })).toBeInTheDocument()
  })
})

describe('header', () => {
  const SUGGESTIONS = {
    Searches: [{ Label: 'Điện thoại', CategorySlug: 'dien-thoai', BrandId: null, ImageUrl: null },
      { Label: 'Điện thoại Samsung', CategorySlug: 'dien-thoai', BrandId: 'b-samsung', ImageUrl: 'https://cdn.example/s26.png' }],
    Products: [{ ProductId: 'p1', Name: 'iPhone 18 Pro Max', Slug: 'iphone-18-pro-max', ImageUrl: null, Price: '20990000.00', OriginalPrice: '24990000.00' }],
  }
  const suggestionCalls = (calls) => calls.filter((call) => call.startsWith('/products/suggestions'))

  test('typing opens suggestions without leaving the page; Enter opens the results page', async () => {
    const calls = mockApi({ '/products/suggestions': () => json(SUGGESTIONS) })
    const router = renderHome()
    const box = await screen.findByRole('searchbox', { name: 'Tìm kiếm sản phẩm' })
    box.focus()
    fireEvent.change(box, { target: { value: 'điện thoại ' } })
    const panel = await screen.findByRole('region', { name: 'Gợi ý tìm kiếm' })
    expect(router.state.location.pathname).toBe('/')
    expect(suggestionCalls(calls)).toEqual(['/products/suggestions?keyword=' + encodeURIComponent('điện thoại').replace(/%20/g, '+')])
    const searches = within(await within(panel).findByRole('region', { name: 'Có phải bạn muốn tìm' })).getAllByRole('link')
    expect(searches.map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['Điện thoại', '/danh-muc/dien-thoai'], ['Điện thoại Samsung', '/danh-muc/dien-thoai?brand=b-samsung']])
    const item = within(within(panel).getByRole('region', { name: 'Sản phẩm gợi ý' })).getByRole('link')
    expect(item).toHaveAttribute('href', '/san-pham/iphone-18-pro-max')
    expect(item).toHaveTextContent('iPhone 18 Pro Max')
    expect(item).toHaveTextContent('20.990.000')
    expect(item.querySelector('del')).toHaveTextContent('24.990.000')
    expect(within(panel).getByRole('link', { name: /Xem tất cả kết quả cho “điện thoại”/ }))
      .toHaveAttribute('href', '/tim-kiem?q=' + encodeURIComponent('điện thoại'))

    fireEvent.submit(box.closest('form'))
    expect(router.state.location.pathname + router.state.location.search).toBe('/tim-kiem?q=' + encodeURIComponent('điện thoại'))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Gợi ý tìm kiếm' })).not.toBeInTheDocument())
    await waitFor(() => expect(box).toHaveValue('điện thoại'))
    await act(async () => router.navigate(-1))
    expect(router.state.location.pathname).toBe('/')
    await waitFor(() => expect(box).toHaveValue(''))
  })

  test('a suggestion opens its page; Escape and the arrow keys work in the list', async () => {
    mockApi({ '/products/suggestions': () => json(SUGGESTIONS), '/categories/slug/dien-thoai': () => json(ROOTS[0]) })
    const router = renderHome()
    const box = await screen.findByRole('searchbox', { name: 'Tìm kiếm sản phẩm' })
    box.focus()
    fireEvent.change(box, { target: { value: 'dien thoai' } })
    const panel = await screen.findByRole('region', { name: 'Gợi ý tìm kiếm' })
    await within(panel).findByRole('link', { name: 'Điện thoại' })
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    expect(within(panel).getByRole('link', { name: 'Điện thoại' })).toHaveFocus()
    fireEvent.keyDown(document.activeElement, { key: 'ArrowDown' })
    expect(within(panel).getByRole('link', { name: 'Điện thoại Samsung' })).toHaveFocus()
    fireEvent.keyDown(document.activeElement, { key: 'Escape' })
    expect(screen.queryByRole('region', { name: 'Gợi ý tìm kiếm' })).not.toBeInTheDocument()
    expect(box).toHaveFocus()
    expect(box).toHaveValue('dien thoai')

    fireEvent.change(box, { target: { value: 'dien thoai s' } })
    await userEvent.click(await within(await screen.findByRole('region', { name: 'Gợi ý tìm kiếm' })).findByRole('link', { name: 'Điện thoại Samsung' }))
    expect(router.state.location.pathname + router.state.location.search).toBe('/danh-muc/dien-thoai?brand=b-samsung')
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Gợi ý tìm kiếm' })).not.toBeInTheDocument())
  })

  test('Vietnamese composition finishes before asking for suggestions, and nothing found says so', async () => {
    const calls = mockApi({ '/products/suggestions': () => json({ Searches: [], Products: [] }) })
    renderHome()
    const box = await screen.findByRole('searchbox', { name: 'Tìm kiếm sản phẩm' })
    box.focus()
    fireEvent.compositionStart(box)
    fireEvent.change(box, { target: { value: 'điện thoại gập' } })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 350)) })
    expect(suggestionCalls(calls)).toEqual([])
    fireEvent.compositionEnd(box)
    expect(await screen.findByText('Không có sản phẩm nào khớp với “điện thoại gập”.')).toBeInTheDocument()
    expect(suggestionCalls(calls)).toHaveLength(1)
  })

  test('an empty box shows recent searches, newest first and without repeats, which can be removed', async () => {
    mockApi({ '/products/suggestions': () => json(SUGGESTIONS) })
    const router = renderHome()
    const box = await screen.findByRole('searchbox', { name: 'Tìm kiếm sản phẩm' })
    for (const text of ['iphone', 'tai nghe', 'IPHONE']) {
      fireEvent.change(box, { target: { value: text } })
      fireEvent.submit(box.closest('form'))
    }
    await act(async () => router.navigate('/'))
    box.blur()
    box.focus()
    const history = await screen.findByRole('region', { name: 'Lịch sử tìm kiếm' })
    expect(within(history).getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')]))
      .toEqual([['IPHONE', '/tim-kiem?q=IPHONE'], ['tai nghe', '/tim-kiem?q=tai%20nghe']])
    fireEvent.click(within(history).getByRole('button', { name: 'Xóa “tai nghe” khỏi lịch sử' }))
    expect(within(history).getAllByRole('link').map((link) => link.textContent)).toEqual(['IPHONE'])
    fireEvent.click(within(history).getByRole('button', { name: 'Xóa tất cả' }))
    expect(screen.queryByRole('region', { name: 'Gợi ý tìm kiếm' })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('vietech:search-history'))).toEqual([])
  })

  test('guests get links to cart, notifications and wishlist; signed-in customers see unread notifications', async () => {
    mockApi()
    renderHome()
    const nav = await screen.findByRole('navigation', { name: 'Tài khoản' })
    expect(within(nav).getByRole('link', { name: 'Giỏ hàng' })).toHaveAttribute('href', '/gio-hang')
    expect(within(nav).getByRole('link', { name: 'Yêu thích' })).toHaveAttribute('href', '/yeu-thich')
    expect(within(nav).getByRole('link', { name: 'Thông báo' })).toHaveAttribute('href', '/thong-bao')
    expect(within(nav).getByRole('button', { name: 'Đăng nhập' })).toBeInTheDocument()
  })

  test('a signed-in customer sees the unread count on the bell', async () => {
    mockApi()
    const auth = makeAuth({ role: 'Customer' })
    renderHome(auth)
    const nav = await screen.findByRole('navigation', { name: 'Tài khoản' })
    expect(await within(nav).findByRole('link', { name: 'Thông báo, 3 chưa đọc' })).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: /Tài khoản/ })).toHaveAttribute('href', '/tai-khoan')
    await waitFor(() => expect(auth.withAccessToken).toHaveBeenCalled())
  })
})

describe('homepage repairs', () => {
  test('best-selling ranks an older item on a later API page in the frontend', async () => {
    const older = { ...DETAILS.p1, ProductId: 'older', Name: 'Sản phẩm bán chạy cũ', Slug: 'ban-chay-cu', SoldQuantity: 5000 }
    const filler = Array.from({ length: 100 }, (_, index) => ({ ...DETAILS.p1, ProductId: `item${index}`, SoldQuantity: 1 }))
    const calls = mockApi({
      '/products': (url) => {
        if (url.searchParams.has('category_id')) return json({ Items: [], Total: 0 })
        if (url.searchParams.get('page_size') !== '100') return json({ Items: [{ ProductId: 'p1' }], Total: 101 })
        return json({ Items: url.searchParams.get('page') === '2' ? [older] : filler, Total: 101 })
      },
      '/products/older': json(older),
      ...Object.fromEntries(filler.map((item) => [`/products/${item.ProductId}`, json(item)])),
    })
    const user = userEvent.setup()
    renderHome()
    const featured = screen.getByRole('region', { name: 'Sản phẩm nổi bật' })
    await within(featured).findByRole('heading', { name: 'iPhone 18 Pro Max' })
    const latestTab = within(featured).getByRole('tab', { name: 'Mới nhất' })
    const bestTab = within(featured).getByRole('tab', { name: 'Bán chạy' })
    expect(latestTab).toHaveAttribute('aria-selected', 'true')
    await user.click(bestTab)
    expect(bestTab).toHaveAttribute('aria-selected', 'true')
    expect(await within(featured).findByRole('heading', { name: 'Sản phẩm bán chạy cũ' })).toBeInTheDocument()
    expect(within(featured).getAllByRole('heading', { level: 3 })[0]).toHaveTextContent('Sản phẩm bán chạy cũ')
    expect(calls).toContain('/products?page=2&page_size=100')
    expect(calls.some((url) => url.includes('sort='))).toBe(false)
    await user.keyboard('{ArrowLeft}')
    expect(latestTab).toHaveFocus()
    expect(latestTab).toHaveAttribute('aria-selected', 'true')
    expect(await within(featured).findByRole('heading', { name: 'iPhone 18 Pro Max' })).toBeInTheDocument()
  })

  test('broken product and banner images use fallbacks without nested links', async () => {
    mockApi({ '/banners': json([{ BannerId: 'bn1', Title: 'Banner có lỗi', ImageUrl: 'https://cdn.example/broken.png', LinkUrl: '/tim-kiem' }]) })
    renderHome()
    const featured = screen.getByRole('region', { name: 'Sản phẩm nổi bật' })
    const card = (await within(featured).findByRole('heading', { name: 'iPhone 18 Pro Max' })).closest('article')
    fireEvent.error(card.querySelector('img'))
    expect(card.querySelector('img')).toBeNull()
    expect(card.querySelector('.pcard-noimage')).toHaveTextContent('VieTech')
    fireEvent.error(await screen.findByRole('img', { name: 'Banner có lỗi' }))
    const carousel = screen.getByRole('region', { name: 'Chương trình nổi bật' })
    expect(within(carousel).getByText('Hình ảnh đang được cập nhật.')).toBeInTheDocument()
    expect(within(carousel).queryAllByRole('img')).toHaveLength(0)
    expect(carousel.querySelector('a a')).toBeNull()
  })

  test('secondary API failures stay visible and news can be retried', async () => {
    let failing = true
    mockApi({ '/news': () => failing ? json({ detail: 'Tin tức đang bận' }, 503)
      : json({ Items: [{ NewsArticleId: 'n1', Title: 'Tin đã tải lại', Slug: 'tin-moi' }], Total: 1 }),
      '/brands': () => json({ detail: 'Thương hiệu đang bận' }, 503),
      '/categories': (url) => url.searchParams.has('parent_id') ? json({ detail: 'Danh mục đang bận' }, 503) : json(ROOTS),
    })
    const user = userEvent.setup()
    renderHome()
    expect(await screen.findByRole('heading', { name: 'Không tải được thương hiệu' })).toBeInTheDocument()
    expect((await screen.findAllByText('Không tải được nhóm danh mục.')).length).toBeGreaterThan(0)
    const news = await screen.findByRole('region', { name: 'Tin tức công nghệ' })
    expect(within(news).getByRole('heading', { name: 'Không tải được tin tức' })).toBeInTheDocument()
    failing = false
    await user.click(within(news).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('link', { name: 'Tin đã tải lại' })).toBeInTheDocument()
  })

  test('footer entries open their own information pages and preserve the store entry', async () => {
    mockApi()
    const router = renderHome()
    const footer = screen.getByRole('contentinfo', { name: 'Chân trang' })
    expect(within(footer).getAllByRole('link')).toHaveLength(12)
    const entries = [['Giới thiệu', 'Giới thiệu VieTech'], ['Liên hệ', 'Liên hệ'], ['Hệ thống cửa hàng', 'Hệ thống cửa hàng'],
      ['Hướng dẫn mua hàng', 'Hướng dẫn mua hàng'], ['Thanh toán', 'Thanh toán'], ['Vận chuyển', 'Vận chuyển'],
      ['Đổi trả & bảo hành', 'Đổi trả & bảo hành'], ['Bảo mật', 'Chính sách bảo mật'], ['Điều khoản sử dụng', 'Điều khoản sử dụng'],
      ['Đổi trả', 'Chính sách đổi trả'], ['Bảo hành', 'Chính sách bảo hành']]
    for (const [label, title] of entries) {
      const href = within(footer).getByRole('link', { name: label, exact: true }).getAttribute('href')
      await act(() => router.navigate(href))
      expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument()
    }
    await act(() => router.navigate('/'))
    const menu = screen.getByRole('navigation', { name: 'Danh mục sản phẩm' })
    expect(within(menu).queryByRole('link', { name: /Sản phẩm đã thích|Khuyến mãi/ })).not.toBeInTheDocument()
  })
})

describe('tidy-up', () => {
  test('leaving the page aborts requests still in flight', async () => {
    const signals = []
    vi.stubGlobal('fetch', vi.fn((input, options) => {
      signals.push(options.signal)
      return new Promise(() => {})
    }))
    const router = renderHome()
    await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    await act(() => router.navigate('/dang-ky'))
    expect(signals.filter(Boolean).length).toBeGreaterThan(0)
    expect(signals.filter(Boolean).every((signal) => signal.aborted)).toBe(true)
  })
})
