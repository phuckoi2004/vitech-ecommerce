import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const reads = vi.hoisted(() => ({ getAdminData: vi.fn() }))
const api = vi.hoisted(() => ({ createShippingMethod: vi.fn(), updateShippingMethod: vi.fn() }))
vi.mock('../../services/api/admin.js', () => reads)
vi.mock('../services/shipping-methods.js', async (original) => ({ ...await original(), ...api }))
const base = { ShippingMethodId: 's1', Code: 'SAME_DAY', Name: 'Giao hàng hỏa tốc', BaseFee: '30000.00', EstimatedDays: 0, IsActive: true }
let rows, readError
beforeEach(() => {
  vi.resetAllMocks(); rows = []; readError = false
  reads.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (readError) throw new Error('Lỗi kết nối vận chuyển')
    if (path === '/shipping-methods') return structuredClone(rows)
    if (path === '/admin/promotions') return { Items: [], Total: 0 }
    const row = rows.find((item) => path === '/shipping-methods/' + item.ShippingMethodId)
    if (row) return structuredClone(row)
    throw new Error('Không tìm thấy phương thức vận chuyển.')
  })
  api.createShippingMethod.mockImplementation(async (_, body) => { const row = { ShippingMethodId: 'server-generated', ...body }; rows.push(row); return row })
  api.updateShippingMethod.mockImplementation(async (_, id, body) => { rows = rows.map((item) => item.ShippingMethodId === id ? { ...item, ...body } : item); return structuredClone(rows.find((item) => item.ShippingMethodId === id)) })
})
function open(path = '/admin/shipping-methods', role = 'Admin') {
  const permissions = ['admin.portal', 'shipping_methods:view', 'promotions:view', ...(role === 'Admin' ? ['shipping_methods:create', 'shipping_methods:update', 'shipping_methods:delete'] : [])]
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
const table = () => within(screen.getByRole('table'))
const loaded = () => screen.findByText('Giao hàng hỏa tốc', {}, { timeout: 5000 })

test('empty list preserves Figma columns and new sidebar entries without sample methods', async () => {
  open()
  await screen.findByText('Chưa có phương thức vận chuyển.', {}, { timeout: 5000 })
  expect(screen.getByRole('heading', { level: 1, name: 'Quản lý phương thức vận chuyển' })).toBeInTheDocument()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Mã', 'Tên phương thức', 'Phí cơ bản', 'Số ngày giao dự kiến', 'Trạng thái', 'Thao tác'])
  expect(screen.getByText('0 phương thức')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 phương thức vận chuyển')).toBeInTheDocument()
  const nav = within(screen.getByRole('navigation', { name: 'Menu quản trị' }))
  expect(nav.getByRole('button', { name: 'Vận chuyển', exact: true })).toHaveAttribute('aria-current', 'page')
  fireEvent.click(nav.getByRole('button', { name: 'Khuyến mãi', exact: true }))
  expect(nav.getByRole('button', { name: 'Mã giảm giá', exact: true })).toBeInTheDocument()
  expect(reads.getAdminData).toHaveBeenCalledWith('access-for-test', '/shipping-methods', { active_only: false }, expect.any(AbortSignal))
})

test('search, status and actual delivery-day options combine; reset clears filters', async () => {
  rows = [base, { ...base, ShippingMethodId: 's2', Code: 'ECONOMY', Name: 'Giao hàng tiết kiệm', EstimatedDays: 7, IsActive: false }]
  const router = open()
  await loaded()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'hoa toc' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Thời gian giao dự kiến' }), { target: { value: '0' } })
  expect(table().getAllByRole('row')).toHaveLength(2)
  expect(router.state.location.search).toContain('days=0')
  fireEvent.change(screen.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'inactive' } })
  await screen.findByText('Không có phương thức vận chuyển phù hợp.')
  fireEvent.click(screen.getByRole('button', { name: 'Đặt lại' }))
  expect(screen.getByRole('searchbox')).toHaveValue('')
  expect(table().getAllByRole('row')).toHaveLength(3)
  expect(screen.getAllByRole('option').some((option) => option.textContent === 'Trong ngày')).toBe(true)
})

test('pagination operates on full filtered list and search resets to first page', async () => {
  rows = Array.from({ length: 11 }, (_, i) => ({ ...base, ShippingMethodId: 's' + i, Code: 'SHIP-' + i, Name: 'Phương thức ' + i }))
  open()
  await screen.findByText('11 phương thức', {}, { timeout: 5000 })
  expect(table().getAllByRole('row')).toHaveLength(6)
  fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
  expect(table().getByText('SHIP-5')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'SHIP-10' } })
  expect(table().getByText('SHIP-10')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 1–1 trong 1 phương thức vận chuyển')).toBeInTheDocument()
})

test('Staff can read inactive methods while all write and removed detail/delete controls are absent', async () => {
  rows = [{ ...base, IsActive: false }]
  open('/admin/shipping-methods', 'Staff')
  await loaded()
  expect(screen.queryByRole('button', { name: '+ Thêm phương thức' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Sửa ' + base.Name })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Xóa ' + base.Name })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Chi tiết ' + base.Name })).not.toBeInTheDocument()
  expect(table().getByText('Trong ngày')).toBeInTheDocument()
  expect(table().getByText('Ngừng hoạt động')).toBeInTheDocument()
  expect(table().queryByRole('button')).not.toBeInTheDocument()
})

test('add form saves local field values to existing API and returns to refreshed list', async () => {
  const router = open()
  await screen.findByText('Chưa có phương thức vận chuyển.', {}, { timeout: 5000 })
  fireEvent.click(screen.getByRole('button', { name: '+ Thêm phương thức' }))
  await screen.findByLabelText('Mã phương thức')
  expect(screen.getByRole('dialog', { name: 'Thêm phương thức vận chuyển' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 1, name: 'Quản lý phương thức vận chuyển' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Mã phương thức'), { target: { value: 'NEW' } })
  fireEvent.change(screen.getByLabelText('Tên phương thức'), { target: { value: 'Giao ngay' } })
  fireEvent.change(screen.getByLabelText('Phí vận chuyển', { exact: true }), { target: { value: '0' } })
  fireEvent.change(screen.getByLabelText(/Số ngày giao dự kiến/), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: 'Thêm phương thức', exact: true }))
  await waitFor(() => expect(api.createShippingMethod).toHaveBeenCalledWith('access-for-test', { Code: 'NEW', Name: 'Giao ngay', BaseFee: '0', EstimatedDays: 0, IsActive: true }))
  await screen.findByText('Đã thêm phương thức vận chuyển.')
  expect(router.state.location.pathname).toBe('/admin/shipping-methods')
  expect(await table().findByText('Giao ngay')).toBeInTheDocument()
})

test('edit preloads values, preserves list filters and updates whole-VND fees and inactive status', async () => {
  rows = [base]; const router = open('/admin/shipping-methods?keyword=SAME_DAY')
  await loaded()
  fireEvent.click(screen.getByRole('button', { name: 'Sửa ' + base.Name }))
  await screen.findByDisplayValue(base.Code)
  const dialog = within(screen.getByRole('dialog', { name: 'Sửa phương thức vận chuyển' }))
  fireEvent.change(screen.getByLabelText('Tên phương thức'), { target: { value: 'Tên đã sửa' } })
  expect(dialog.getByLabelText('Phí vận chuyển cơ bản')).toHaveAttribute('step', '1')
  fireEvent.change(dialog.getByLabelText('Phí vận chuyển cơ bản'), { target: { value: '12345' } })
  fireEvent.change(dialog.getByLabelText('Trạng thái'), { target: { value: 'false' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
  await waitFor(() => expect(api.updateShippingMethod).toHaveBeenCalledWith('access-for-test', 's1', expect.objectContaining({ Name: 'Tên đã sửa', BaseFee: '12345', EstimatedDays: 0, IsActive: false })))
  await screen.findByText('Đã cập nhật phương thức vận chuyển.')
  expect(router.state.location.search).toBe('?keyword=SAME_DAY')
  expect(await table().findByText('Tên đã sửa')).toBeInTheDocument()
  expect(table().getByText('Ngừng hoạt động')).toBeInTheDocument()
})

test('table only offers edit and toggle; obsolete delete query cannot open a dialog', async () => {
  rows = [base]; open('/admin/shipping-methods?dialog=delete&method=s1'); await loaded()
  expect(table().getAllByRole('button').map((button) => button.getAttribute('aria-label'))).toEqual(['Sửa ' + base.Name, 'Ngừng hoạt động ' + base.Name])
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Ngừng hoạt động ' + base.Name }))
  await waitFor(() => expect(api.updateShippingMethod).toHaveBeenCalledWith('access-for-test', 's1', { IsActive: false }))
  expect(await table().findByText('Ngừng hoạt động')).toBeInTheDocument()
  expect(table().getByRole('button', { name: 'Kích hoạt ' + base.Name })).toBeInTheDocument()
})

test('failed status update keeps existing row and status and allows retry', async () => {
  rows = [base]; api.updateShippingMethod.mockRejectedValueOnce(new Error('Không cập nhật được trạng thái.'))
  open(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Ngừng hoạt động ' + base.Name }))
  await screen.findByRole('alert')
  expect(table().getByText('Đang hoạt động')).toBeInTheDocument()
  expect(rows).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Ngừng hoạt động ' + base.Name }))
  expect(await table().findByText('Ngừng hoạt động')).toBeInTheDocument()
})

test('activation prevents duplicate requests and refreshes active-status filter', async () => {
  rows = [{ ...base, IsActive: false }]
  let finish
  api.updateShippingMethod.mockImplementationOnce(() => new Promise((resolve) => { finish = () => { rows = [{ ...base, IsActive: true }]; resolve(rows[0]) } }))
  open('/admin/shipping-methods?status=inactive'); await loaded()
  const button = screen.getByRole('button', { name: 'Kích hoạt ' + base.Name })
  fireEvent.click(button); fireEvent.click(button)
  expect(button).toBeDisabled()
  expect(api.updateShippingMethod).toHaveBeenCalledTimes(1)
  expect(api.updateShippingMethod).toHaveBeenCalledWith('access-for-test', 's1', { IsActive: true })
  finish()
  await screen.findByText('Không có phương thức vận chuyển phù hợp.')
  expect(screen.getByText('0 phương thức')).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: 'Trạng thái' })).toHaveValue('inactive')
})

test('coupon sidebar child opens the coupon list from the discount group', async () => {
  open(); await screen.findByText('Chưa có phương thức vận chuyển.', {}, { timeout: 5000 })
  reads.getAdminData.mockClear()
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Khuyến mãi', exact: true }))
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Mã giảm giá', exact: true }))
  await screen.findByRole('heading', { level: 1, name: 'Quản lý mã giảm giá' })
  expect(await screen.findByText('Chưa có mã giảm giá.')).toBeInTheDocument()
  expect(reads.getAdminData.mock.calls.some(([, path]) => path === '/admin/promotions')).toBe(true)
})

test('list failures remain recoverable', async () => {
  readError = true; open()
  await screen.findByText('Lỗi kết nối vận chuyển', {}, { timeout: 5000 })
  expect(screen.queryByText('0 phương thức')).not.toBeInTheDocument()
  readError = false
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Chưa có phương thức vận chuyển.')
})

test('selecting the shipping sidebar again refreshes data and clears filters', async () => {
  rows = [base]; open(); await loaded()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'SAME_DAY' } })
  rows = []
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Vận chuyển', exact: true }))
  await screen.findByText('Chưa có phương thức vận chuyển.')
  expect(screen.getByRole('searchbox')).toHaveValue('')
})

test.each(['/admin/shipping-methods/new', '/admin/shipping-methods/s1/edit'])('Staff cannot use write route %s', async (path) => {
  rows = [base]; open(path, 'Staff')
  await screen.findByRole('heading', { name: 'Không có quyền truy cập' })
  expect(screen.queryByLabelText('Mã phương thức')).not.toBeInTheDocument()
  expect(api.createShippingMethod).not.toHaveBeenCalled()
  expect(api.updateShippingMethod).not.toHaveBeenCalled()
})

test.each(['Hủy', 'Đóng', 'Escape', 'backdrop'])('edit overlay closes with %s without saving and retains filters', async (action) => {
  rows = [base]; const router = open('/admin/shipping-methods/s1/edit?keyword=SAME_DAY&days=0')
  await screen.findByDisplayValue(base.Code, {}, { timeout: 5000 })
  const modal = screen.getByRole('dialog', { name: 'Sửa phương thức vận chuyển' })
  fireEvent.change(within(modal).getByLabelText('Tên phương thức'), { target: { value: 'Chưa lưu' } })
  if (action === 'Escape') fireEvent(modal, new Event('cancel', { cancelable: true }))
  else if (action === 'backdrop') fireEvent.click(modal)
  else fireEvent.click(within(modal).getByRole('button', { name: action, exact: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(router.state.location.pathname).toBe('/admin/shipping-methods')
  expect(router.state.location.search).toBe('?keyword=SAME_DAY&days=0')
  expect(api.updateShippingMethod).not.toHaveBeenCalled()
  expect(rows[0].Name).toBe(base.Name)
})

test('save failure retains entered values and supports retry while duplicate submit and closing are blocked', async () => {
  rows = [base]; api.updateShippingMethod.mockRejectedValueOnce(new Error('Mã phương thức đã tồn tại.'))
  open('/admin/shipping-methods/s1/edit'); await screen.findByDisplayValue(base.Code, {}, { timeout: 5000 })
  const modal = screen.getByRole('dialog'), dialog = within(modal)
  fireEvent.change(dialog.getByLabelText('Mã phương thức'), { target: { value: 'DUPLICATE' } })
  fireEvent.click(dialog.getByRole('button', { name: 'Lưu thay đổi' }))
  await dialog.findByText('Mã phương thức đã tồn tại.')
  expect(dialog.getByLabelText('Mã phương thức')).toHaveValue('DUPLICATE')
  expect(rows[0].Code).toBe(base.Code)
  let finish
  api.updateShippingMethod.mockImplementationOnce((_, id, body) => new Promise((resolve) => { finish = () => { rows = [{ ...base, ...body }]; resolve(rows[0]) } }))
  const submit = dialog.getByRole('button', { name: 'Lưu thay đổi' })
  fireEvent.click(submit); fireEvent.click(submit)
  expect(api.updateShippingMethod).toHaveBeenCalledTimes(2)
  expect(dialog.getByLabelText('Mã phương thức')).toBeDisabled()
  expect(dialog.getByRole('button', { name: 'Hủy' })).toBeDisabled()
  expect(dialog.getByRole('button', { name: 'Đóng' })).toBeDisabled()
  fireEvent(modal, new Event('cancel', { cancelable: true })); fireEvent.click(modal)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  finish()
  await screen.findByText('Đã cập nhật phương thức vận chuyển.')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(await table().findByText('DUPLICATE')).toBeInTheDocument()
})

test('missing edit data shows error inside overlay with working close and no empty writable form', async () => {
  open('/admin/shipping-methods/missing/edit')
  const modal = await screen.findByRole('dialog', { name: 'Sửa phương thức vận chuyển' }, { timeout: 5000 })
  await within(modal).findByText('Không tìm thấy phương thức vận chuyển.')
  expect(within(modal).queryByLabelText('Mã phương thức')).not.toBeInTheDocument()
  fireEvent.click(within(modal).getByRole('button', { name: 'Đóng' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})
