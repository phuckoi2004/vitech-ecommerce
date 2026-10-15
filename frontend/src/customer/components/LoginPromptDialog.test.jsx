import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { expect, test } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import LoginPage from '../pages/LoginPage.jsx'
import RegisterPage from '../pages/RegisterPage.jsx'
import WishlistLink from './WishlistLink.jsx'

function renderAt(path, auth = makeAuth()) {
  const router = createMemoryRouter([
    { path: '/', element: <WishlistLink /> },
    { path: '/yeu-thich', element: <p>Trang yêu thích</p> },
    { path: '/dang-nhap', element: <LoginPage /> },
    { path: '/dang-ky', element: <RegisterPage /> },
  ], { initialEntries: [path] })
  render(<AuthContext.Provider value={auth}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

test('a visitor opening the wishlist is asked to sign in or register and returns to the wishlist afterwards', async () => {
  const router = renderAt('/')
  fireEvent.click(screen.getByRole('link', { name: 'Yêu thích' }))
  const prompt = await screen.findByRole('dialog', { name: 'Bạn đã có tài khoản chưa?' })
  expect(router.state.location.pathname).toBe('/')
  expect(within(prompt).getByRole('link', { name: 'Đăng nhập' })).toHaveAttribute('href', '/dang-nhap?next=%2Fyeu-thich')
  fireEvent.click(within(prompt).getByRole('link', { name: 'Đăng ký' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/dang-ky'))
  expect(router.state.location.search).toBe('?next=%2Fyeu-thich')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('signed-in customers open the wishlist directly', async () => {
  const router = renderAt('/', makeAuth({ role: 'Customer' }))
  fireEvent.click(screen.getByRole('link', { name: 'Yêu thích' }))
  expect(await screen.findByText('Trang yêu thích')).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/yeu-thich')
})

test('sign-up links to sign-in with the same return page', () => {
  renderAt('/dang-ky?next=%2Fsan-pham%2Fdien-thoai')
  expect(screen.getByRole('link', { name: 'Đăng nhập' })).toHaveAttribute('href', '/dang-nhap?next=%2Fsan-pham%2Fdien-thoai')
})

test('sign-in links to sign-up with the same return page', () => {
  renderAt('/dang-nhap?next=%2Fsan-pham%2Fdien-thoai')
  expect(screen.getByRole('link', { name: 'Đăng ký ngay' })).toHaveAttribute('href', '/dang-ky?next=%2Fsan-pham%2Fdien-thoai')
})

test('an unsafe return address is not forwarded', () => {
  renderAt('/dang-ky?next=https%3A%2F%2Fevil.example')
  expect(screen.getByRole('link', { name: 'Đăng nhập' })).toHaveAttribute('href', '/dang-nhap')
})
