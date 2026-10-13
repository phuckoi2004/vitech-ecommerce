// Guards and login pages with the real AuthProvider; the session API module and page API modules are mocked.
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { appRoutes } from '../routes.jsx'
import AuthProvider from './AuthProvider.jsx'

const api = vi.hoisted(() => ({ current: {} }))

vi.mock('../lib/auth-api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const call = (name) => (...args) => api.current[name](...args)
  return {
    ...actual,
    cancelPendingRefresh: call('cancelPendingRefresh'),
    clearLocalCsrf: call('clearLocalCsrf'),
    loginCustomer: call('loginCustomer'),
    loginInternal: call('loginInternal'),
    logoutSession: call('logoutSession'),
    readCsrfToken: call('readCsrfToken'),
    renewSession: call('renewSession'),
  }
})

vi.mock('../lib/account-api.js', async (importOriginal) => ({
  ...(await importOriginal()),
  getDefaultAddress: vi.fn(async () => null),
  changePassword: vi.fn(async () => ({ message: 'Đã đổi mật khẩu' })),
  getProfile: vi.fn(async () => session('Admin').user),
}))

vi.mock('../lib/admin-users-api.js', () => ({
  listUsers: vi.fn(async () => ({ Items: [], Total: 0, Page: 1, PageSize: 20 })),
  getUser: vi.fn(), getUserDefaultAddress: vi.fn(), createStaff: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(),
}))

function session(role) {
  return {
    access_token: `${role}-access`, csrf_token: `${role}-csrf`,
    user: { UserId: `${role}-id`, Role: role, FullName: `${role} for test`, PhoneNumber: '0912345678', Email: `${role.toLowerCase()}@example.com` },
    permissions: role === 'Admin' ? ['admin.portal', 'users:read', 'users:manage'] : role === 'Staff' ? ['admin.portal'] : ['customer.portal'],
  }
}

// `restored` is the session found in the refresh cookie at startup (null: signed out).
function setup(path, { restored = null } = {}) {
  api.current = {
    cancelPendingRefresh: vi.fn(),
    clearLocalCsrf: vi.fn(),
    loginCustomer: vi.fn(async () => session('Customer')),
    loginInternal: vi.fn(async () => session('Admin')),
    logoutSession: vi.fn(async () => ({ message: 'Đã đăng xuất' })),
    readCsrfToken: () => (restored ? 'csrf-cookie' : ''),
    renewSession: vi.fn(async () => restored),
  }
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  render(<AuthProvider><RouterProvider router={router} /></AuthProvider>)
  return router
}

const location = (router) => `${router.state.location.pathname}${router.state.location.search}`

async function fillCustomerLogin() {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText(/Email \/ Số điện thoại/), 'khach@example.com')
  await user.type(screen.getByLabelText(/^Mật khẩu/), 'Password1!')
  await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))
}

beforeEach(() => {
  document.title = ''
})

describe('customer sign-in', () => {
  test('a protected customer page sends the visitor to sign in and back to the page afterwards', async () => {
    const router = setup('/tai-khoan')
    await waitFor(() => expect(location(router)).toBe('/dang-nhap?next=%2Ftai-khoan'))
    await fillCustomerLogin()
    await waitFor(() => expect(router.state.location.pathname).toBe('/tai-khoan'))
    expect(await screen.findByRole('heading', { name: 'Thông tin cá nhân' })).toBeInTheDocument()
    expect(api.current.loginCustomer).toHaveBeenCalledWith('khach@example.com', 'Password1!')
  })

  test.each([
    ['https://evil.example/', 'another site'],
    ['//evil.example/path', 'a protocol-relative URL'],
    ['/admin/users', 'the internal area'],
  ])('next=%s (%s) is ignored and sign-in goes home', async (next) => {
    const router = setup(`/dang-nhap?next=${encodeURIComponent(next)}`)
    await fillCustomerLogin()
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
  })

  test('the header shows the signed-in customer after an in-app sign-in', async () => {
    const router = setup('/dang-nhap')
    await fillCustomerLogin()
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
    expect(await screen.findByRole('link', { name: /Tài khoản/ })).toHaveAttribute('href', '/tai-khoan')
  })
})

describe('internal sign-in', () => {
  test('a Customer session opening /admin/users gets the internal login and returns to the page after signing in', async () => {
    const router = setup('/admin/users', { restored: session('Customer') })
    expect(await screen.findByRole('heading', { name: 'Đăng nhập hệ thống' })).toBeInTheDocument()
    expect(location(router)).toBe('/admin/login?next=%2Fadmin%2Fusers')
    expect(api.current.logoutSession).not.toHaveBeenCalled()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Số điện thoại / Email'), 'admin@example.com')
    await user.type(screen.getByLabelText('Mật khẩu'), 'Password1!')
    await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/admin/users'))
    expect(await screen.findByRole('region', { name: 'Quản lý tài khoản' })).toBeInTheDocument()
  })

  test('signing out of the internal area opens the internal login without next', async () => {
    const router = setup('/admin/users', { restored: session('Admin') })
    await screen.findByRole('region', { name: 'Quản lý tài khoản' })
    await act(async () => screen.getByRole('button', { name: 'Đăng xuất' }).click())
    await waitFor(() => expect(location(router)).toBe('/admin/login'))
    expect(api.current.logoutSession).toHaveBeenCalledWith('Admin-access', 'Admin-csrf')
    expect(await screen.findByRole('heading', { name: 'Đăng nhập hệ thống' })).toBeInTheDocument()
  })

  test('the reset form keeps next when going back to the login form', async () => {
    const router = setup('/admin/login?next=%2Fadmin%2Fprofile')
    await act(async () => (await screen.findByRole('button', { name: 'Quên mật khẩu?' })).click())
    expect(location(router)).toBe('/admin/forgot-password?next=%2Fadmin%2Fprofile')
    await act(async () => screen.getByRole('button', { name: 'Quay lại đăng nhập' }).click())
    expect(location(router)).toBe('/admin/login?next=%2Fadmin%2Fprofile')
    await act(() => router.navigate(-1))
    expect(router.state.location.pathname).toBe('/admin/forgot-password')
  })
})

describe('ending a customer session on the account page', () => {
  test('sign-out goes to the home page', async () => {
    const router = setup('/tai-khoan', { restored: session('Customer') })
    const menu = await screen.findByRole('navigation', { name: 'Mục tài khoản' })
    await act(async () => within(menu).getByRole('button', { name: 'Đăng xuất' }).click())
    await waitFor(() => expect(location(router)).toBe('/'))
    expect(api.current.logoutSession).toHaveBeenCalledWith('Customer-access', 'Customer-csrf')
    expect(screen.getByRole('button', { name: 'Đăng nhập' })).toBeInTheDocument()
  })

  test('a password change ends the session and opens sign-in with the password-changed notice', async () => {
    const router = setup('/tai-khoan', { restored: session('Customer') })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Đổi mật khẩu' }))
    await user.type(screen.getByLabelText('Mật khẩu hiện tại'), 'OldPassword1!')
    await user.type(screen.getByLabelText('Mật khẩu mới'), 'NewPassword1!')
    await user.type(screen.getByLabelText('Xác nhận mật khẩu mới'), 'NewPassword1!')
    const dialog = screen.getByRole('dialog', { name: 'Đổi mật khẩu' })
    await user.click(within(dialog).getByRole('button', { name: 'Đổi mật khẩu' }))
    await waitFor(() => expect(location(router)).toBe('/dang-nhap?doi-mat-khau=1'))
    expect(await screen.findByText('Đã đổi mật khẩu thành công. Vui lòng đăng nhập lại bằng mật khẩu mới.')).toBeInTheDocument()
    expect(api.current.clearLocalCsrf).toHaveBeenCalled()
  })
})
