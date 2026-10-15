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

afterEach(() => {
  vi.unstubAllGlobals()
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
    mockApi()
    renderHome()

    const menu = await screen.findByRole('navigation', { name: 'Danh mục sản phẩm' })
    expect(await within(menu).findByRole('link', { name: 'Điện thoại' })).toHaveAttribute('href', '/danh-muc/dien-thoai')

    const newest = screen.getByRole('region', { name: 'Sản phẩm nổi bật' })
    const iphone = (await within(newest).findByRole('heading', { name: 'iPhone 18 Pro Max' })).closest('a')
    expect(iphone).toHaveAttribute('href', '/san-pham/iphone-18-pro-max')
    expect(iphone).toHaveTextContent('Từ 20.990.000 ₫')
    expect(iphone).toHaveTextContent('4,8')
    expect(iphone).toHaveTextContent('Đã bán 1,2k')
    const galaxy = within(newest).getByRole('heading', { name: 'Galaxy S26 Ultra' }).closest('a')
    expect(galaxy).toHaveTextContent('Hết hàng')
    expect(galaxy).toHaveTextContent('31.490.000 ₫')
    expect(galaxy).not.toHaveTextContent('Từ')

    const shortcuts = screen.getByRole('region', { name: 'Mua sắm theo danh mục' })
    expect(await within(shortcuts).findByText('2 sản phẩm')).toBeInTheDocument()
    expect(within(shortcuts).getAllByText('Sắp có hàng')).toHaveLength(2)
    expect(within(shortcuts).getByRole('link', { name: 'Mua ngay: Laptop' })).toHaveAttribute('href', '/danh-muc/laptop')

    expect(await screen.findByRole('link', { name: /Chọn điện thoại năm 2026/ })).toHaveAttribute('href', '/tin-tuc/chon-dien-thoai')
    const brands = screen.getByRole('region', { name: 'Thương hiệu nổi bật' })
    expect(within(brands).getByRole('link', { name: 'Samsung' })).toHaveAttribute('href', '/thuong-hieu/samsung')

    // Empty banner data keeps the area without displaying sample product images.
    const hero = screen.getByRole('region', { name: 'Danh mục và chương trình nổi bật' })
    expect(within(hero).getByRole('status')).toHaveTextContent('Chưa có chương trình nổi bật.')
    expect(document.body).not.toHaveTextContent(/Giảm \d+%|Trả góp/)
    expect(screen.queryByRole('heading', { name: 'Tư vấn mua hàng', exact: true })).not.toBeInTheDocument()
  })

  test('tabs switch categories; sub-category and brand chips filter the row', async () => {
    const calls = mockApi()
    const user = userEvent.setup()
    renderHome()

    const showcase = await screen.findByRole('region', { name: 'Điện thoại, Laptop' })
    const panel = within(showcase).getByRole('tabpanel')
    expect(await within(panel).findByRole('heading', { name: 'Galaxy S26 Ultra' })).toBeInTheDocument()
    expect(within(panel).getByRole('heading', { name: 'iPhone 18 Pro Max' })).toBeInTheDocument()

    await user.click(within(panel).getByRole('button', { name: 'Apple' }))
    await waitFor(() => expect(within(panel).queryByRole('heading', { name: 'Galaxy S26 Ultra' })).not.toBeInTheDocument())
    expect(calls).toContain('/products?category_id=c-phone&brand_id=b-apple&include_descendants=true&page=1&page_size=10')
    expect(within(panel).getByRole('button', { name: 'Apple' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(within(panel).getByRole('button', { name: 'Điện thoại chơi game' }))
    expect(await within(panel).findByRole('heading', { name: 'Galaxy S26 Ultra' })).toBeInTheDocument()
    expect(within(panel).queryByRole('heading', { name: 'iPhone 18 Pro Max' })).not.toBeInTheDocument()
    expect(calls).toContain('/products?category_id=c-gaming&include_descendants=true&page=1&page_size=10')
    expect(within(panel).getByRole('link', { name: /Xem tất cả/ })).toHaveAttribute('href', '/danh-muc/dien-thoai-choi-game')

    await user.click(within(showcase).getByRole('tab', { name: 'Laptop' }))
    expect(within(showcase).getByRole('tab', { name: 'Laptop' })).toHaveAttribute('aria-selected', 'true')
    expect(await within(showcase).findByRole('heading', { name: 'Chưa có sản phẩm' })).toBeInTheDocument()

    // A single remaining root category gets a heading instead of tabs.
    expect(screen.getByRole('heading', { level: 2, name: 'Tai nghe' })).toBeInTheDocument()
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
    await user.click(within(carousel).getByRole('button', { name: 'Banner tiếp theo' }))
    expect(within(carousel).getByRole('button', { name: 'Xem banner 1' })).toHaveAttribute('aria-current', 'true')
    await user.click(within(carousel).getByRole('button', { name: 'Banner trước' }))
    expect(within(carousel).getByRole('button', { name: 'Xem banner 2' })).toHaveAttribute('aria-current', 'true')
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

describe('header', () => {
  test('search opens the search page with the keyword; an empty search does nothing', async () => {
    mockApi()
    const user = userEvent.setup()
    const router = renderHome()

    const box = await screen.findByRole('searchbox', { name: 'Tìm kiếm sản phẩm' })
    await user.click(screen.getByRole('button', { name: 'Tìm kiếm' }))
    expect(router.state.location.pathname).toBe('/')
    await user.type(box, '  iphone 18  ')
    await user.click(screen.getByRole('button', { name: 'Tìm kiếm' }))
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe('/tim-kiem?q=iphone%2018')
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
      '/brands': json({ detail: 'Thương hiệu đang bận' }, 503),
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
