// Route table and guards with a given session (AuthContext value); the API modules used by pages are mocked.
import { act, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, test, vi } from 'vitest'
import { AuthContext } from './auth/context.js'
import { appRoutes } from './routes.jsx'
import { makeAuth } from './test/auth.js'

vi.mock('./lib/admin-users-api.js', () => ({
  listUsers: vi.fn(async () => ({ Items: [], Total: 0, Page: 1, PageSize: 20 })),
  getUser: vi.fn(), getUserDefaultAddress: vi.fn(), createStaff: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(),
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
  test('a signed-in Admin opens /admin/users directly', async () => {
    const router = renderAt('/admin/users', makeAuth({ role: 'Admin' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Quản lý tài khoản' })).toBeInTheDocument()
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
    await act(async () => within(menu).getByRole('button', { name: 'Quản lý tài khoản' }).click())
    expect(router.state.location.pathname).toBe('/admin/users')
    await act(() => router.navigate(-1))
    expect(router.state.location.pathname).toBe('/admin')
    expect(await screen.findByRole('heading', { level: 1, name: 'Tổng quan' })).toBeInTheDocument()
  })
})

describe('guards', () => {
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
    expect(await screen.findByRole('heading', { level: 1, name: 'Tổng quan' })).toBeInTheDocument()
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
    expect(menuEntries()).toEqual(['Tổng quan', 'Quản lý tài khoản'])
  })

  test('Staff without users:read sees only the entries it may use', async () => {
    renderAt('/admin', makeAuth({ role: 'Staff' }))
    await screen.findByRole('navigation', { name: 'Menu quản trị' })
    expect(menuEntries()).toEqual(['Tổng quan'])
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
