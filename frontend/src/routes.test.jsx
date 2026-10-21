// Route table and guards with a given session (AuthContext value); the API modules used by pages are mocked.
import { act, render, screen, within } from '@testing-library/react'
import { createBrowserRouter, createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, test, vi } from 'vitest'
import { AuthContext } from './auth/context.js'
import { appRoutes } from './routes.jsx'
import { makeAuth } from './test/auth.js'

vi.mock('./lib/admin-users-api.js', () => ({
  listUsers: vi.fn(async () => ({ Items: [], Total: 0, Page: 1, PageSize: 20 })),
  getUser: vi.fn(), getUserDefaultAddress: vi.fn(), createStaff: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(),
}))

vi.mock('./services/api/admin.js', () => ({
  getAdminData: vi.fn(async (token, path) => path.endsWith('/statistics/orders')
    ? { TotalOrders: 0, ByStatus: { Pending: 0 } }
    : path.endsWith('/unread-count') ? { Count: 0 } : { Items: [], Total: 0, Page: 1, PageSize: 20 }),
  getRevenueSeries: vi.fn(async (token, months) => months.map((month) => ({ month, data: { OrderCount: 0, NetRevenue: '0.00' }, error: '' }))),
  getDashboardStock: vi.fn(async () => ({ Items: [], Total: 0 })),
  markNotificationRead: vi.fn(), markAllNotificationsRead: vi.fn(),
}))

vi.mock('./lib/account-api.js', async (importOriginal) => ({
  ...(await importOriginal()),
  getDefaultAddress: vi.fn(async () => null),
  getProfile: vi.fn(async () => ({ FullName: 'Admin for test', Email: 'admin@example.com', PhoneNumber: '0912345678', Role: 'Admin' })),
}))

function renderAt(path, auth = makeAuth()) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={auth}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

const location = (router) => `${router.state.location.pathname}${router.state.location.search}`

describe('existing URLs', () => {
  test.each([
    ['/dang-nhap', 'Đăng nhập'],
    ['/dang-ky', 'Đăng ký tài khoản'],
    ['/quen-mat-khau', 'Quên mật khẩu'],
    ['/admin/login', 'Đăng nhập hệ thống'],
    ['/admin/forgot-password', 'Quên mật khẩu'],
  ])('%s still opens its page', async (path, heading) => {
    const router = renderAt(path)
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(path)
  })

  test('the home page renders inside the customer layout', async () => {
    renderAt('/')
    expect(await screen.findByRole('link', { name: 'VieTech – Trang chủ' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('button', { name: 'Đăng nhập' })).toBeInTheDocument()
  })
})

describe('deep links and history', () => {
  test('native browser back and forward switch internal auth pages and preserve next', async () => {
    const originalUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`
    const originalState = window.history.state
    const search = '?next=%2Fadmin%2Fusers%3Fpage%3D2'
    window.history.replaceState(null, '', `/admin/login${search}`)
    const router = createBrowserRouter(appRoutes)
    const view = render(<AuthContext.Provider value={makeAuth()}><RouterProvider router={router} /></AuthContext.Provider>)
    // Unlike memory-router tests, real history traversal dispatches the browser's popstate event.
    async function traverse(delta) {
      await act(async () => {
        const popped = new Promise((resolve) => window.addEventListener('popstate', resolve, { once: true }))
        window.history.go(delta)
        await popped
      })
    }
    try {
      expect(await screen.findByRole('heading', { name: 'Đăng nhập hệ thống' })).toBeInTheDocument()
      await act(async () => screen.getByRole('button', { name: 'Quên mật khẩu?' }).click())
      expect(await screen.findByRole('heading', { name: 'Quên mật khẩu' })).toBeInTheDocument()
      expect(location(router)).toBe(`/admin/forgot-password${search}`)
      expect(`${window.location.pathname}${window.location.search}`).toBe(location(router))
      expect(document.title).toBe('Quên mật khẩu | VieTech')

      await traverse(-1)
      expect(await screen.findByRole('heading', { name: 'Đăng nhập hệ thống' })).toBeInTheDocument()
      expect(location(router)).toBe(`/admin/login${search}`)
      expect(`${window.location.pathname}${window.location.search}`).toBe(location(router))
      expect(document.title).toBe('Đăng nhập nội bộ | VieTech')

      await traverse(1)
      expect(await screen.findByRole('heading', { name: 'Quên mật khẩu' })).toBeInTheDocument()
      expect(location(router)).toBe(`/admin/forgot-password${search}`)
      expect(`${window.location.pathname}${window.location.search}`).toBe(location(router))
      expect(document.title).toBe('Quên mật khẩu | VieTech')
    } finally {
      view.unmount()
      router.dispose()
      window.history.replaceState(originalState, '', originalUrl)
    }
  })

  test('native browser login redirect keeps the address bar synchronized with next', async () => {
    const originalUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`
    const originalState = window.history.state
    window.history.replaceState(null, '', '/admin/login?next=%2Fadmin%2Fusers%3Fpage%3D2')
    const router = createBrowserRouter(appRoutes)
    const view = render(<AuthContext.Provider value={makeAuth({ role: 'Admin' })}><RouterProvider router={router} /></AuthContext.Provider>)
    try {
      expect(await screen.findByRole('heading', { level: 1, name: 'Tài khoản' })).toBeInTheDocument()
      expect(location(router)).toBe('/admin/users?page=2')
      expect(`${window.location.pathname}${window.location.search}`).toBe(location(router))
    } finally {
      view.unmount()
      router.dispose()
      window.history.replaceState(originalState, '', originalUrl)
    }
  })

  test('a signed-in Admin opens /admin/users directly', async () => {
    const router = renderAt('/admin/users', makeAuth({ role: 'Admin' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Tài khoản' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Quản lý tài khoản' })).toBeInTheDocument()
    expect(location(router)).toBe('/admin/users')
  })

  test('/admin/profile opens the profile section for Staff', async () => {
    renderAt('/admin/profile', makeAuth({ role: 'Staff' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Thông tin cá nhân' })).toBeInTheDocument()
  })

  test('back and forward move between visited pages', async () => {
    const router = renderAt('/')
    await screen.findByRole('link', { name: 'VieTech – Trang chủ' })
    await act(() => router.navigate('/dang-ky'))
    expect(await screen.findByRole('heading', { name: 'Đăng ký tài khoản' })).toBeInTheDocument()
    await act(() => router.navigate(-1))
    expect(router.state.location.pathname).toBe('/')
    expect(await screen.findByRole('link', { name: 'VieTech – Trang chủ' })).toBeInTheDocument()
    await act(() => router.navigate(1))
    expect(router.state.location.pathname).toBe('/dang-ky')
    expect(await screen.findByRole('heading', { name: 'Đăng ký tài khoản' })).toBeInTheDocument()
  })

  test('the menu changes the URL and the browser history', async () => {
    const router = renderAt('/admin', makeAuth({ role: 'Admin' }))
    const menu = await screen.findByRole('navigation', { name: 'Menu quản trị' })
    await act(async () => within(menu).getByRole('button', { name: 'Tài khoản' }).click())
    expect(router.state.location.pathname).toBe('/admin/users')
    await act(() => router.navigate(-1))
    expect(router.state.location.pathname).toBe('/admin')
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
  })
})

describe('guards', () => {
  test('the return creation page requires sign-in and preserves the intended URL', async () => {
    const router = renderAt('/doi-tra/tao-yeu-cau')
    expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
    expect(location(router)).toBe('/dang-nhap?next=%2Fdoi-tra%2Ftao-yeu-cau')
  })

  test('the warranty creation page requires customer sign-in and preserves its URL', async () => {
    const router = renderAt('/bao-hanh/tao-yeu-cau')
    expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
    expect(location(router)).toBe('/dang-nhap?next=%2Fbao-hanh%2Ftao-yeu-cau')
  })

  test('a signed-out visitor of a customer page signs in with the page kept in next', async () => {
    const router = renderAt('/tai-khoan')
    expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
    expect(location(router)).toBe('/dang-nhap?next=%2Ftai-khoan')
  })

  test('a signed-out visitor of an internal page gets the internal login with next', async () => {
    const router = renderAt('/admin/users?page=2')
    expect(await screen.findByRole('heading', { name: 'Đăng nhập hệ thống' })).toBeInTheDocument()
    expect(location(router)).toBe('/admin/login?next=%2Fadmin%2Fusers%3Fpage%3D2')
  })

  test('a Customer cannot use internal routes: the internal login form is shown and the session is kept', async () => {
    const auth = makeAuth({ role: 'Customer' })
    const router = renderAt('/admin/users', auth)
    expect(await screen.findByRole('heading', { name: 'Đăng nhập hệ thống' })).toBeInTheDocument()
    expect(location(router)).toBe('/admin/login?next=%2Fadmin%2Fusers')
    expect(screen.queryByRole('navigation', { name: 'Menu quản trị' })).not.toBeInTheDocument()
    expect(auth.signOut).not.toHaveBeenCalled()
    expect(auth.endSession).not.toHaveBeenCalled()
  })

  test.each(['Staff', 'Admin'])('%s on /tai-khoan sees a notice with a link to /admin, without redirect or sign-out', async (role) => {
    const auth = makeAuth({ role })
    const router = renderAt('/tai-khoan', auth)
    expect(await screen.findByRole('heading', { name: 'Bạn đang đăng nhập bằng tài khoản nội bộ' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Đến khu vực quản trị' })).toHaveAttribute('href', '/admin')
    expect(location(router)).toBe('/tai-khoan')
    expect(auth.signOut).not.toHaveBeenCalled()
    expect(auth.endSession).not.toHaveBeenCalled()
  })

  test('a signed-in Staff/Admin opening the internal login goes to next or the internal home', async () => {
    const router = renderAt('/admin/login?next=%2Fadmin%2Fprofile', makeAuth({ role: 'Staff' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Thông tin cá nhân' })).toBeInTheDocument()
    expect(location(router)).toBe('/admin/profile')
  })

  test('next cannot leave the internal area from the internal login', async () => {
    const router = renderAt('/admin/login?next=https%3A%2F%2Fevil.example%2F', makeAuth({ role: 'Admin' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
    expect(location(router)).toBe('/admin')
  })
})

describe('internal menu', () => {
  function menuEntries() {
    return within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getAllByRole('button').map((button) => button.textContent)
  }

  test('Admin with users:read sees account management', async () => {
    renderAt('/admin', makeAuth({ role: 'Admin' }))
    await screen.findByRole('navigation', { name: 'Menu quản trị' })
    expect(menuEntries()).toEqual(['Tổng quan', 'Tài khoản'])
  })

  test('Staff without users:read sees only the entries it may use', async () => {
    renderAt('/admin', makeAuth({ role: 'Staff' }))
    await screen.findByRole('navigation', { name: 'Menu quản trị' })
    expect(menuEntries()).toEqual(['Tổng quan', 'Đơn hàng'])
  })

  test('the product dropdown navigates to its permitted page and supports history', async () => {
    const router = renderAt('/admin', makeAuth({ role: 'Admin', permissions: ['admin.portal', 'products:view', 'categories:view'] }))
    const menu = await screen.findByRole('navigation', { name: 'Menu quản trị' })
    const group = within(menu).getByRole('button', { name: 'Sản phẩm' })
    expect(group).toHaveAttribute('aria-expanded', 'false')
    await act(async () => group.click())
    expect(group).toHaveAttribute('aria-expanded', 'true')
    await act(async () => within(menu).getByRole('button', { name: 'Danh sách sản phẩm' }).click())
    expect(location(router)).toBe('/admin/products')
    expect(await screen.findByRole('heading', { level: 1, name: 'Danh sách sản phẩm' })).toBeInTheDocument()
    await act(() => router.navigate(-1))
    expect(location(router)).toBe('/admin')
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
  })

  test('an ungranted product deep link is blocked by the permission guard', async () => {
    renderAt('/admin/products', makeAuth({ role: 'Staff', permissions: ['admin.portal'] }))
    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Phân trang' })).not.toBeInTheDocument()
  })

  test('Staff uses the same dashboard with its permitted modules and no Admin-only menu items', async () => {
    renderAt('/admin', makeAuth({ role: 'Staff', permissions: ['admin.portal', 'products:view', 'categories:view', 'brands:view', 'orders:view', 'purchases:view', 'suppliers:view', 'inventory:view', 'returns:view', 'warranties:view', 'revenue_reports:view', 'chat:view', 'payment_methods:view'] }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
    const menu = within(screen.getByRole('navigation', { name: 'Menu quản trị' }))
    for (const name of ['Tài khoản', 'Đánh giá', 'Tin tức & Banner']) expect(menu.queryByRole('button', { name })).not.toBeInTheDocument()
    for (const name of ['Sản phẩm', 'Đơn hàng', 'Nhập hàng', 'Nhà cung cấp', 'Đổi trả', 'Bảo hành', 'Báo cáo thống kê', 'Hỗ trợ khách hàng', 'Thanh toán']) expect(menu.getByRole('button', { name })).toBeInTheDocument()
    expect(menu.queryByRole('button', { name: 'Kho hàng' })).not.toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Lãi gộp' })).toBeInTheDocument()
    expect(screen.queryByRole('article', { name: 'Số đơn đã giao' })).not.toBeInTheDocument()
    expect(screen.queryByRole('article', { name: 'Số đơn hủy' })).not.toBeInTheDocument()
  })

  test('resource tabs follow URL history and do not leak when switching sidebar sections', async () => {
    const router = renderAt('/admin/inventory', makeAuth({ role: 'Staff', permissions: ['admin.portal', 'inventory:view', 'orders:view'] }))
    await screen.findByRole('heading', { level: 1, name: 'Kho hàng' })
    await act(async () => screen.getByRole('button', { name: 'Sắp hết hàng' }).click())
    expect(location(router)).toBe('/admin/inventory?tab=low-stock')
    expect(await screen.findByRole('heading', { level: 3, name: 'Sắp hết hàng' })).toBeInTheDocument()
    const menu = within(screen.getByRole('navigation', { name: 'Menu quản trị' }))
    await act(async () => menu.getByRole('button', { name: 'Đơn hàng' }).click())
    expect(location(router)).toBe('/admin/orders')
    expect(await screen.findByRole('columnheader', { name: 'Mã đơn' })).toBeInTheDocument()
    await act(() => router.navigate(-1))
    expect(location(router)).toBe('/admin/inventory?tab=low-stock')
    expect(await screen.findByRole('heading', { level: 3, name: 'Sắp hết hàng' })).toBeInTheDocument()
  })

  test('a permission is not inferred from the role: an Admin session without users:read has no account management', async () => {
    renderAt('/admin/users', makeAuth({ role: 'Admin', permissions: ['admin.portal'] }))
    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeInTheDocument()
    expect(menuEntries()).toEqual(['Tổng quan'])
    expect(screen.queryByRole('region', { name: 'Quản lý tài khoản' })).not.toBeInTheDocument()
  })

  test('Staff opening /admin/users directly sees a permission message instead of the section', async () => {
    renderAt('/admin/users', makeAuth({ role: 'Staff' }))
    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeInTheDocument()
  })
})

describe('unknown URLs', () => {
  test('an unknown customer URL shows the 404 page without redirecting home', async () => {
    const router = renderAt('/khong-ton-tai')
    expect(await screen.findByRole('heading', { name: 'Không tìm thấy trang' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Về trang chủ' })).toHaveAttribute('href', '/')
    expect(location(router)).toBe('/khong-ton-tai')
    expect(document.title).toBe('Không tìm thấy trang | VieTech')
  })

  test.each([[null], ['Admin']])('an unknown internal URL shows the 404 page (role: %s)', async (role) => {
    const router = renderAt('/admin/khong-ton-tai', makeAuth({ role }))
    expect(await screen.findByRole('heading', { name: 'Không tìm thấy trang' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Về trang quản trị' })).toHaveAttribute('href', '/admin')
    expect(location(router)).toBe('/admin/khong-ton-tai')
  })
})
