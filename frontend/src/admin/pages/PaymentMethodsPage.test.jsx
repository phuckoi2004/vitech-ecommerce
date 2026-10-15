import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), createPaymentMethod: vi.fn(), updatePaymentMethod: vi.fn(), deletePaymentMethod: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData, getDashboardStock: async () => ({ Items: [], Total: 0 }), getRevenueSeries: async () => [] }))
vi.mock('../services/payment-methods.js', async (original) => ({ ...await original(), ...Object.fromEntries(Object.entries(api).filter(([key]) => key !== 'getAdminData')) }))
const permissions = ['admin.portal', 'payment_methods:view', 'payment_methods:create', 'payment_methods:update', 'payment_methods:delete']
const method = { PaymentMethodId: 'pm1', Code: 'COD', Name: 'Thanh toán khi nhận hàng', Description: 'Khách hàng thanh toán trực tiếp khi nhận hàng.', IsActive: true, DisplayOrder: 1 }
let methods
function renderPage(path = '/admin/payments', role = 'Admin', granted = permissions) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
beforeEach(() => {
  vi.resetAllMocks(); methods = []
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/payment-methods') return structuredClone(methods)
    if (path === '/admin/payment-transactions') return { Items: [], Total: 0 }
    const row = methods.find((item) => path === '/payment-methods/' + item.PaymentMethodId)
    if (row) return structuredClone(row)
    throw new Error('Không tìm thấy phương thức thanh toán.')
  })
  api.createPaymentMethod.mockImplementation(async (_, body) => { const row = { ...body, PaymentMethodId: 'new' }; methods.push(row); return row })
  api.updatePaymentMethod.mockImplementation(async (_, id, body) => { methods = methods.map((row) => row.PaymentMethodId === id ? { ...row, ...body } : row); return methods.find((row) => row.PaymentMethodId === id) })
  api.deletePaymentMethod.mockImplementation(async (_, id) => { methods = methods.filter((row) => row.PaymentMethodId !== id) })
})

test('empty data retains six columns and an accurate zero count without example methods', async () => {
  renderPage()
  await screen.findByText('Chưa có phương thức thanh toán.')
  expect(screen.getByRole('heading', { level: 1, name: 'Quản lý thanh toán' })).toBeInTheDocument()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Mã', 'Tên phương thức', 'Mô tả / hướng dẫn', 'Trạng thái', 'Thứ tự', 'Thao tác'])
  expect(screen.getByText('0 phương thức')).toBeInTheDocument()
  expect(screen.queryByText('COD')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thanh toán', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/payment-methods', { active_only: false }, expect.any(AbortSignal))
})

test('renders complete active/inactive API data, server ordering and safe text descriptions', async () => {
  methods = [method, { ...method, PaymentMethodId: 'pm2', Code: 'QR', Name: 'Chuyển khoản QR', IsActive: false, Description: '<script>untrusted()</script>', DisplayOrder: 2 }]
  renderPage()
  await screen.findByText('2 phương thức')
  const table = within(screen.getByRole('table'))
  expect(table.getByText('Hoạt động')).toBeInTheDocument()
  expect(table.getByText('Ngừng hoạt động')).toBeInTheDocument()
  expect(table.getByText('<script>untrusted()</script>')).toBeInTheDocument()
  expect(screen.getByRole('table').querySelector('script')).toBeNull()
  expect(table.getAllByRole('row').slice(1).map((row) => row.firstChild.textContent)).toEqual(['COD', 'QR'])
})

test('refresh and retry load server changes without displaying a fabricated count during failure', async () => {
  const original = api.getAdminData.getMockImplementation()
  let fail = true
  api.getAdminData.mockImplementation((...args) => args[1] === '/payment-methods' && fail ? Promise.reject(new Error('Không tải được danh sách.')) : original(...args))
  renderPage()
  await screen.findByText('Không tải được danh sách.')
  expect(screen.queryByText('0 phương thức')).not.toBeInTheDocument()
  fail = false; methods = [method]
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('1 phương thức')
  methods = []
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByText('Chưa có phương thức thanh toán.')
})

test('create validates fields, preserves form after conflicts and saves only the API fields', async () => {
  const router = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Thêm phương thức' }))
  const ui = within(await screen.findByRole('region', { name: 'Thêm phương thức thanh toán' }))
  expect(router.state.location.pathname).toBe('/admin/payments/new')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.change(ui.getByRole('textbox', { name: 'Mã phương thức' }), { target: { value: '   ' } })
  fireEvent.change(ui.getByRole('textbox', { name: 'Tên phương thức' }), { target: { value: 'Tên thật' } })
  fireEvent.click(ui.getByRole('button', { name: 'Lưu phương thức' }))
  await ui.findByText('Vui lòng nhập mã, tên phương thức và thứ tự hiển thị là số nguyên hợp lệ.')
  expect(api.createPaymentMethod).not.toHaveBeenCalled()
  fireEvent.change(ui.getByRole('textbox', { name: 'Mã phương thức' }), { target: { value: ' qr ' } })
  fireEvent.change(ui.getByRole('combobox'), { target: { value: 'inactive' } })
  fireEvent.change(ui.getByRole('spinbutton'), { target: { value: '3' } })
  api.createPaymentMethod.mockRejectedValueOnce(new Error('Mã phương thức thanh toán đã tồn tại'))
  fireEvent.click(ui.getByRole('button', { name: 'Lưu phương thức' }))
  const error = await screen.findByRole('dialog', { name: 'Thay đổi thất bại' })
  expect(within(error).getByText('Mã phương thức thanh toán đã tồn tại')).toBeInTheDocument()
  fireEvent.click(within(error).getByRole('button', { name: 'Đóng' }))
  expect(ui.getByRole('textbox', { name: 'Tên phương thức' })).toHaveValue('Tên thật')
  fireEvent.change(ui.getByRole('textbox', { name: 'Mã phương thức' }), { target: { value: ' bank_qr ' } })
  fireEvent.click(ui.getByRole('button', { name: 'Lưu phương thức' }))
  const success = await screen.findByRole('dialog', { name: 'Cập nhật thành công' })
  expect(api.createPaymentMethod).toHaveBeenLastCalledWith('access-for-test', { Code: 'BANK_QR', Name: 'Tên thật', Description: null, IsActive: false, DisplayOrder: 3 })
  expect(router.state.location.pathname).toBe('/admin/payments/new')
  fireEvent.click(within(success).getByRole('button', { name: 'Đóng' }))
  await screen.findByRole('heading', { level: 1, name: 'Quản lý thanh toán' })
  expect(router.state.location.pathname).toBe('/admin/payments')
})

test('editing keeps the processing code intact and atomically sends content, status and ordering', async () => {
  methods = [method]
  renderPage('/admin/payments?dialog=edit&method=pm1')
  const ui = within(await screen.findByRole('region', { name: 'Sửa phương thức thanh toán' }))
  expect(await ui.findByRole('textbox', { name: 'Mã phương thức' })).toHaveAttribute('readonly')
  expect(ui.getAllByRole('option').map((item) => item.textContent)).toEqual(['Hoạt động', 'Ngừng hoạt động'])
  fireEvent.change(ui.getByRole('textbox', { name: 'Tên phương thức' }), { target: { value: 'COD đã cập nhật' } })
  fireEvent.change(ui.getByRole('textbox', { name: 'Mô tả / hướng dẫn' }), { target: { value: '' } })
  fireEvent.change(ui.getByRole('combobox'), { target: { value: 'inactive' } })
  fireEvent.change(ui.getByRole('spinbutton'), { target: { value: '4' } })
  fireEvent.click(ui.getByRole('button', { name: 'Cập nhật' }))
  await screen.findByRole('dialog', { name: 'Cập nhật thành công' })
  expect(api.updatePaymentMethod).toHaveBeenCalledWith('access-for-test', 'pm1', { Name: 'COD đã cập nhật', Description: null, IsActive: false, DisplayOrder: 4 })
  expect(methods[0].Code).toBe('COD')
})

test('deletion requires confirmation, shows in-use rejection and supports hiding through edit', async () => {
  methods = [method]
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa ' + method.Name }))
  let ui = within(screen.getByRole('dialog', { name: 'Xóa phương thức thanh toán?' }))
  fireEvent.click(await ui.findByRole('button', { name: 'Hủy' }))
  expect(api.deletePaymentMethod).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Xóa ' + method.Name }))
  ui = within(screen.getByRole('dialog'))
  api.deletePaymentMethod.mockRejectedValueOnce(new Error('Phương thức thanh toán đang được sử dụng'))
  fireEvent.click(await ui.findByRole('button', { name: 'Xác nhận xóa' }))
  const error = await screen.findByRole('dialog', { name: 'Thay đổi thất bại' })
  expect(within(error).getByText('Phương thức thanh toán đang được sử dụng')).toBeInTheDocument()
  expect(methods).toHaveLength(1)
  fireEvent.click(within(error).getByRole('button', { name: 'Đóng' }))
  fireEvent.click(screen.getByRole('button', { name: 'Sửa ' + method.Name }))
  ui = within(await screen.findByRole('region', { name: 'Sửa phương thức thanh toán' }))
  fireEvent.change(await ui.findByRole('combobox'), { target: { value: 'inactive' } })
  fireEvent.click(ui.getByRole('button', { name: 'Cập nhật' }))
  await screen.findByRole('dialog', { name: 'Cập nhật thành công' })
  expect(methods[0].IsActive).toBe(false)
})

test('pending deletion blocks repeated clicks, Escape and cancel; success refreshes the list', async () => {
  methods = [method]
  renderPage('/admin/payments?dialog=delete&method=pm1')
  const dialog = await screen.findByRole('dialog'), ui = within(dialog)
  let finish
  api.deletePaymentMethod.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const confirm = await ui.findByRole('button', { name: 'Xác nhận xóa' })
  fireEvent.click(confirm); fireEvent.click(confirm)
  expect(api.deletePaymentMethod).toHaveBeenCalledTimes(1)
  expect(ui.getByRole('button', { name: 'Hủy' })).toBeDisabled()
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  expect(dialog).toBeInTheDocument()
  await act(() => { methods = []; finish() })
  await screen.findByRole('dialog', { name: 'Cập nhật thành công' })
  await screen.findByText('0 phương thức')
})

test('Staff can read inactive methods but cannot open write dialogs', async () => {
  methods = [method]
  const router = renderPage('/admin/payments?dialog=delete&method=pm1', 'Staff', ['admin.portal', 'payment_methods:view'])
  await screen.findByText('1 phương thức')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '+ Thêm phương thức' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Sửa ' + method.Name })).not.toBeInTheDocument()
  for (const mode of ['new', 'edit']) { await act(() => router.navigate('/admin/payments?dialog=' + mode + '&method=pm1')); expect(screen.queryByRole('dialog')).not.toBeInTheDocument() }
  expect(api.createPaymentMethod).not.toHaveBeenCalled()
  expect(api.deletePaymentMethod).not.toHaveBeenCalled()
})

test('view-only Admin cannot edit through a deep link and the home breadcrumb navigates to the dashboard', async () => {
  methods = [method]
  const router = renderPage('/admin/payments?dialog=edit&method=pm1', 'Admin', ['admin.portal', 'payment_methods:view'])
  await screen.findByText('1 phương thức')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Sửa ' + method.Name })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Trang chủ', exact: true }))
  await screen.findByRole('heading', { level: 1, name: 'Dashboard' })
  expect(router.state.location.pathname).toBe('/admin')
  expect(api.updatePaymentMethod).not.toHaveBeenCalled()
})

test('missing detail never opens an editable empty record and transaction bookmarks still work', async () => {
  const router = renderPage('/admin/payments?dialog=edit&method=missing')
  await screen.findByText('Không tìm thấy phương thức thanh toán.')
  expect(screen.queryByRole('textbox', { name: 'Tên phương thức' })).not.toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Về danh sách phương thức thanh toán' }))
  await act(() => router.navigate('/admin/payments?tab=1'))
  await screen.findByRole('heading', { level: 3, name: 'Giao dịch' })
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/payment-transactions', expect.any(Object), expect.any(AbortSignal))
  fireEvent.click(screen.getByRole('button', { name: 'Phương thức thanh toán', exact: true }))
  await screen.findByRole('heading', { level: 2, name: 'Phương thức thanh toán' })
  expect(router.state.location.search).toBe('')
})

test('new and edit routes reload directly, keep sidebar and return to the list on cancel without writes', async () => {
  methods = [method]
  const router = renderPage('/admin/payments/pm1/edit?origin=methods')
  const editor = within(await screen.findByRole('region', { name: 'Sửa phương thức thanh toán' }))
  expect(editor.getByRole('textbox', { name: 'Tên phương thức' })).toHaveValue(method.Name)
  expect(screen.getByRole('heading', { level: 1, name: 'Sửa phương thức thanh toán' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thanh toán', exact: true })).toHaveAttribute('aria-current', 'page')
  fireEvent.click(editor.getByRole('button', { name: 'Hủy' }))
  await screen.findByRole('heading', { level: 1, name: 'Quản lý thanh toán' })
  expect(router.state.location.pathname).toBe('/admin/payments')
  expect(router.state.location.search).toBe('?origin=methods')
  fireEvent.click(screen.getByRole('button', { name: '+ Thêm phương thức' }))
  const create = within(await screen.findByRole('region', { name: 'Thêm phương thức thanh toán' }))
  fireEvent.click(create.getByRole('button', { name: 'Hủy' }))
  expect(api.createPaymentMethod).not.toHaveBeenCalled()
  expect(api.updatePaymentMethod).not.toHaveBeenCalled()
})

test('failed update retries the same payload once while busy, then success stays above the form until closed', async () => {
  methods = [method]
  const router = renderPage('/admin/payments/pm1/edit')
  const editor = within(await screen.findByRole('region', { name: 'Sửa phương thức thanh toán' }))
  fireEvent.change(editor.getByRole('textbox', { name: 'Tên phương thức' }), { target: { value: 'Tên sửa chưa mất' } })
  api.updatePaymentMethod.mockRejectedValueOnce(new Error('Lỗi lưu dữ liệu.'))
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  const error = await screen.findByRole('dialog', { name: 'Thay đổi thất bại' }), ui = within(error)
  expect(ui.getByText('Hệ thống không thể lưu thay đổi phương thức thanh toán. Vui lòng thử lại.')).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/admin/payments/pm1/edit')
  expect(editor.getByRole('textbox', { name: 'Tên phương thức' })).toHaveValue('Tên sửa chưa mất')
  let finish
  api.updatePaymentMethod.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const retry = ui.getByRole('button', { name: 'Thử lại' })
  fireEvent.click(retry); fireEvent.click(retry)
  expect(api.updatePaymentMethod).toHaveBeenCalledTimes(2)
  expect(api.updatePaymentMethod.mock.calls[1]).toEqual(api.updatePaymentMethod.mock.calls[0])
  expect(ui.getByRole('button', { name: 'Đóng' })).toBeDisabled()
  fireEvent(error, new Event('cancel', { cancelable: true }))
  expect(error).toBeInTheDocument()
  await act(() => { methods[0] = { ...method, Name: 'Tên sửa chưa mất' }; finish(methods[0]) })
  const success = await screen.findByRole('dialog', { name: 'Cập nhật thành công' })
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(router.state.location.pathname).toBe('/admin/payments/pm1/edit')
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  expect(api.updatePaymentMethod).toHaveBeenCalledTimes(2)
  fireEvent.click(within(success).getByRole('button', { name: 'Đóng' }))
  await screen.findByText('Tên sửa chưa mất')
  expect(router.state.location.pathname).toBe('/admin/payments')
})

test('deletion preview uses server data and failure retry replaces confirmation without stacking modals', async () => {
  methods = [{ ...method, IsActive: false }]
  renderPage('/admin/payments?dialog=delete&method=pm1')
  const confirm = within(await screen.findByRole('dialog', { name: 'Xóa phương thức thanh toán?' }))
  await confirm.findByText('COD • Thanh toán khi nhận hàng')
  expect(confirm.getByText('Trạng thái hiện tại: Ngừng hoạt động')).toBeInTheDocument()
  api.deletePaymentMethod.mockRejectedValueOnce(new Error('Chưa xóa được phương thức.'))
  fireEvent.click(confirm.getByRole('button', { name: 'Xác nhận xóa' }))
  const error = within(await screen.findByRole('dialog', { name: 'Thay đổi thất bại' }))
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(error.getByText('Hệ thống không thể xóa phương thức thanh toán. Vui lòng thử lại.')).toBeInTheDocument()
  fireEvent.click(error.getByRole('button', { name: 'Thử lại' }))
  const success = within(await screen.findByRole('dialog', { name: 'Cập nhật thành công' }))
  expect(api.deletePaymentMethod).toHaveBeenCalledTimes(2)
  fireEvent.click(success.getByRole('button', { name: 'Đóng' }))
  await screen.findByText('0 phương thức')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('direct form routes enforce write permission without exposing an editable draft', async () => {
  const router = renderPage('/admin/payments/new', 'Staff', ['admin.portal', 'payment_methods:view'])
  expect(screen.queryByRole('textbox', { name: 'Mã phương thức' })).not.toBeInTheDocument()
  await act(() => router.navigate('/admin/payments/pm1/edit'))
  expect(screen.queryByRole('textbox', { name: 'Tên phương thức' })).not.toBeInTheDocument()
  expect(api.createPaymentMethod).not.toHaveBeenCalled()
  expect(api.updatePaymentMethod).not.toHaveBeenCalled()
})
