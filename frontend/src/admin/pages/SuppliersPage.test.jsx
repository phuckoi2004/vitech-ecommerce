import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'
import SuppliersPage from './SuppliersPage.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), createSupplier: vi.fn(), updateSupplier: vi.fn(), hideSupplier: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/suppliers.js', async (original) => ({ ...await original(), createSupplier: api.createSupplier, updateSupplier: api.updateSupplier, hideSupplier: api.hideSupplier }))

const supplier = { SupplierId: 's1', SupplierCode: 'NCC-NGUOI-DUNG', Name: 'Nhà cung cấp từ API', Email: 'contact@supplier.vn', PhoneNumber: '028 7300 0001', Address: 'Địa chỉ từ API', TaxCode: '0312345678', Note: 'Ghi chú từ API', IsActive: true }
const hidden = { ...supplier, SupplierId: 's2', SupplierCode: 'NCC-CU', Name: 'Đối tác đã ẩn', PhoneNumber: '028 7300 0099', Email: null, TaxCode: null, IsActive: false }
const permissions = ['admin.portal', 'suppliers:view', 'suppliers:create', 'suppliers:update', 'suppliers:delete']
let suppliers

function renderPage(path = '/admin/suppliers', granted = permissions, routes) {
  const router = createMemoryRouter(routes ?? [{ path: '/admin/suppliers', element: <SuppliersPage /> }], { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Admin', permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

beforeEach(() => {
  vi.resetAllMocks()
  suppliers = []
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/suppliers') return { Items: structuredClone(suppliers.slice((query.page - 1) * query.page_size, query.page * query.page_size)), Total: suppliers.length }
    if (['/admin/purchase-orders', '/admin/statistics/inventory', '/admin/inventory/low-stock'].includes(path)) return { Items: [], Total: 0 }
    const found = suppliers.find((item) => path === '/admin/suppliers/' + item.SupplierId)
    if (found) return { ...found }
    throw new Error('Không tìm thấy nhà cung cấp.')
  })
  api.createSupplier.mockImplementation(async (_, body) => { const saved = { ...body, SupplierId: 'new-id' }; suppliers.push(saved); return saved })
  api.updateSupplier.mockImplementation(async (_, id, body) => { suppliers = suppliers.map((item) => item.SupplierId === id ? { ...item, ...body } : item); return suppliers.find((item) => item.SupplierId === id) })
  api.hideSupplier.mockImplementation(async (_, id) => { suppliers = suppliers.map((item) => item.SupplierId === id ? { ...item, IsActive: false } : item); return suppliers.find((item) => item.SupplierId === id) })
})

test('empty API data keeps all six columns, zero count and no sample suppliers', async () => {
  renderPage()
  await screen.findByText('Chưa có nhà cung cấp.')
  for (const name of ['Mã NCC', 'Tên nhà cung cấp', 'Liên hệ', 'Mã số thuế', 'Trạng thái', 'Thao tác']) expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
  expect(screen.getByText('0 nhà cung cấp')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 nhà cung cấp')).toBeInTheDocument()
  expect(screen.queryByText('Apple Distribution VN')).not.toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/suppliers', { active_only: false, page: 1, page_size: 100 }, expect.any(AbortSignal))
})

test('table displays user supplied supplier codes, contacts, tax values, badges and icon actions', async () => {
  suppliers = [supplier, hidden]
  renderPage()
  await screen.findByText('2 nhà cung cấp')
  const table = within(screen.getByRole('table'))
  expect(table.getByText('NCC-NGUOI-DUNG')).toBeInTheDocument()
  expect(table.getByText('contact@supplier.vn')).toBeInTheDocument()
  expect(table.getByText('0312345678')).toBeInTheDocument()
  expect(table.getByText('Hoạt động')).toBeInTheDocument()
  expect(table.getByText('Ẩn')).toBeInTheDocument()
  expect(table.getByRole('button', { name: 'Xóa Đối tác đã ẩn' })).toBeDisabled()
  expect(table.getByRole('button', { name: 'Chi tiết Nhà cung cấp từ API' }).querySelector('img')).toHaveAttribute('width', '18')
})

test('search covers later API pages, ignores Vietnamese accents and combines with inactive filtering', async () => {
  suppliers = Array.from({ length: 100 }, (_, index) => ({ ...supplier, SupplierId: 'bulk-' + index, Name: 'Hãng ' + index }))
  suppliers.push({ ...hidden, SupplierId: 'last', Name: 'Đối tác tận cuối', Email: 'last@supplier.vn' })
  const router = renderPage()
  await screen.findByText('101 nhà cung cấp')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/suppliers', { active_only: false, page: 2, page_size: 100 }, expect.any(AbortSignal))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'doi tac tan cuoi' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'hidden' } })
  fireEvent.submit(screen.getByRole('search'))
  await screen.findByText('1 nhà cung cấp')
  expect(screen.getByText('Đối tác tận cuối')).toBeInTheDocument()
  expect(router.state.location.search).toBe('?keyword=doi+tac+tan+cuoi&status=hidden')
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  await screen.findByText('101 nhà cung cấp')
  expect(screen.getByRole('searchbox')).toHaveValue('')
  await act(() => router.navigate(-1))
  expect(screen.getByRole('searchbox')).toHaveValue('doi tac tan cuoi')
  expect(screen.getByRole('combobox', { name: 'Trạng thái' })).toHaveValue('hidden')
})

test.each(['NCC-NGUOI-DUNG', 'contact@supplier.vn', '02873000001'])('search matches code/email/formatted telephone %s', async (keyword) => {
  suppliers = [supplier, hidden]
  renderPage('/admin/suppliers?keyword=' + encodeURIComponent(keyword))
  await screen.findByText('1 nhà cung cấp')
  expect(screen.getByText(supplier.Name)).toBeInTheDocument()
})

test('client pagination counts filtered results, resets on search and clamps old deep links', async () => {
  suppliers = Array.from({ length: 7 }, (_, index) => ({ ...supplier, SupplierId: 'p' + index, Name: 'NCC ' + index }))
  const router = renderPage('/admin/suppliers?page=99')
  await waitFor(() => expect(router.state.location.search).toBe('?page=2'))
  await screen.findByText('Hiển thị 6–7 trong 7 nhà cung cấp')
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(3)
  fireEvent.click(screen.getByRole('button', { name: 'Trang trước' }))
  await screen.findByText('Hiển thị 1–5 trong 7 nhà cung cấp')
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(6)
})

test('errors distinguish an unavailable directory from an empty list and retry loads all pages again', async () => {
  api.getAdminData.mockRejectedValueOnce(new Error('Không kết nối được máy chủ.'))
  renderPage()
  await screen.findByText('Không kết nối được máy chủ.')
  expect(screen.queryByText('0 nhà cung cấp')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Chưa có nhà cung cấp.')
})

test('creation sends supported fields, keeps the supplier code chosen by the user and clears optional blanks to null', async () => {
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Thêm nhà cung cấp' }))
  const dialog = screen.getByRole('dialog', { name: 'Thêm nhà cung cấp' })
  for (const [label, value] of [['Mã nhà cung cấp', 'NCC-TU-DAT'], ['Tên nhà cung cấp', 'Nhà cung cấp mới'], ['Số điện thoại', '028 7300 0001'], ['Địa chỉ', 'Địa chỉ mới']]) fireEvent.change(within(dialog).getByRole('textbox', { name: label }), { target: { value } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm nhà cung cấp', exact: true }))
  await waitFor(() => expect(api.createSupplier).toHaveBeenCalledWith('access-for-test', { SupplierCode: 'NCC-TU-DAT', Name: 'Nhà cung cấp mới', PhoneNumber: '028 7300 0001', Email: null, Address: 'Địa chỉ mới', TaxCode: null, Note: null, IsActive: true }))
  await screen.findByText('NCC-TU-DAT')
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

test('detail reads all API fields and edit can restore a hidden supplier and clear optional values', async () => {
  suppliers = [{ ...supplier, IsActive: false }]
  renderPage('/admin/suppliers?status=hidden')
  fireEvent.click(await screen.findByRole('button', { name: 'Chi tiết Nhà cung cấp từ API' }))
  let dialog = await screen.findByRole('dialog', { name: 'Chi tiết nhà cung cấp' })
  await within(dialog).findByText('Địa chỉ từ API')
  expect(within(dialog).getByText('Ghi chú từ API')).toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Sửa nhà cung cấp' }))
  dialog = screen.getByRole('dialog', { name: 'Sửa nhà cung cấp' })
  await within(dialog).findByRole('textbox', { name: 'Mã nhà cung cấp' })
  for (const name of ['Email', 'Mã số thuế', 'Ghi chú']) fireEvent.change(within(dialog).getByRole('textbox', { name }), { target: { value: '' } })
  fireEvent.change(within(dialog).getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'active' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  await waitFor(() => expect(api.updateSupplier).toHaveBeenCalledWith('access-for-test', 's1', { SupplierCode: supplier.SupplierCode, Name: supplier.Name, PhoneNumber: supplier.PhoneNumber, Address: supplier.Address, Email: null, TaxCode: null, Note: null, IsActive: true }))
  await screen.findByText('Không có nhà cung cấp phù hợp.')
})

test('soft deletion needs explicit confirmation, keeps the record and preserves filter state', async () => {
  suppliers = [supplier]
  const router = renderPage('/admin/suppliers?status=active')
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa Nhà cung cấp từ API' }))
  let dialog = screen.getByRole('dialog', { name: 'Xóa mềm nhà cung cấp' })
  await within(dialog).findByRole('button', { name: 'Xác nhận xóa mềm' })
  expect(api.hideSupplier).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Hủy' }))
  fireEvent.click(screen.getByRole('button', { name: 'Xóa Nhà cung cấp từ API' }))
  dialog = screen.getByRole('dialog')
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Xác nhận xóa mềm' }))
  await waitFor(() => expect(api.hideSupplier).toHaveBeenCalledWith('access-for-test', 's1'))
  await screen.findByText('Không có nhà cung cấp phù hợp.')
  expect(suppliers).toHaveLength(1)
  expect(suppliers[0].IsActive).toBe(false)
  expect(router.state.location.search).toBe('?status=active')
})

test('duplicate-code failures retain typed fields and permit correction without losing the form', async () => {
  suppliers = [supplier]
  api.updateSupplier.mockRejectedValueOnce(new Error('Mã nhà cung cấp đã tồn tại'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa Nhà cung cấp từ API' }))
  const dialog = screen.getByRole('dialog')
  const code = await within(dialog).findByRole('textbox', { name: 'Mã nhà cung cấp' })
  fireEvent.change(code, { target: { value: 'MA-TRUNG' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Mã nhà cung cấp đã tồn tại')
  expect(code).toHaveValue('MA-TRUNG')
  fireEvent.change(code, { target: { value: 'MA-MOI' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  await screen.findByText('MA-MOI')
})

test('busy writes disable submit and modal dismissal and guard programmatic repeated submissions', async () => {
  suppliers = [supplier]
  let finish
  api.updateSupplier.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa Nhà cung cấp từ API' }))
  const dialog = screen.getByRole('dialog')
  await within(dialog).findByRole('textbox', { name: 'Mã nhà cung cấp' })
  fireEvent.submit(dialog.querySelector('form'))
  expect(within(dialog).getByRole('button', { name: 'Hủy' })).toBeDisabled()
  fireEvent.submit(dialog.querySelector('form'))
  expect(api.updateSupplier).toHaveBeenCalledTimes(1)
  await act(async () => finish(supplier))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

test('blank required fields and invalid emails are rejected before a write', async () => {
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Thêm nhà cung cấp' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.submit(dialog.querySelector('form'))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Mã nhà cung cấp không được để trống')
  for (const [label, value] of [['Mã nhà cung cấp', 'M'], ['Tên nhà cung cấp', 'N'], ['Số điện thoại', '02873000001'], ['Địa chỉ', 'Địa chỉ'], ['Email', 'khong-hop-le']]) fireEvent.change(within(dialog).getByRole('textbox', { name: label }), { target: { value } })
  fireEvent.submit(dialog.querySelector('form'))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Email nhà cung cấp không hợp lệ')
  expect(api.createSupplier).not.toHaveBeenCalled()
})

test('view-only sessions cannot open write dialogs from query strings or mutate suppliers', async () => {
  suppliers = [supplier]
  const router = renderPage('/admin/suppliers?dialog=new', ['admin.portal', 'suppliers:view'])
  await screen.findByText('1 nhà cung cấp')
  for (const mode of ['new', 'edit', 'delete']) {
    await act(() => router.navigate('/admin/suppliers?dialog=' + mode + '&supplier=s1'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: /Thêm nhà cung cấp|Sửa Nhà cung cấp|Xóa Nhà cung cấp/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Chi tiết Nhà cung cấp từ API' }))
  const dialog = screen.getByRole('dialog', { name: 'Chi tiết nhà cung cấp' })
  await within(dialog).findByText('Địa chỉ từ API')
  expect(within(dialog).queryByRole('button', { name: 'Sửa nhà cung cấp' })).not.toBeInTheDocument()
  for (const write of [api.createSupplier, api.updateSupplier, api.hideSupplier]) expect(write).not.toHaveBeenCalled()
})

test('supplier route is standalone in the old inventory position and purchases has no supplier tab', async () => {
  const router = renderPage('/admin/suppliers', [...permissions, 'purchases:view', 'inventory:view', 'orders:view'], adminRoutes)
  await screen.findByRole('heading', { level: 1, name: 'Quản lý nhà cung cấp' })
  const nav = within(screen.getByRole('navigation', { name: 'Menu quản trị' }))
  const supplierItem = nav.getByRole('button', { name: 'Nhà cung cấp', exact: true })
  expect(supplierItem).toHaveAttribute('aria-current', 'page')
  expect(supplierItem).not.toHaveAttribute('aria-expanded')
  expect(nav.queryByRole('button', { name: 'Kho hàng' })).not.toBeInTheDocument()
  const names = nav.getAllByRole('button').map((button) => button.textContent)
  expect(names.indexOf('Nhà cung cấp')).toBe(names.indexOf('Nhập hàng') + 1)
  fireEvent.click(nav.getByRole('button', { name: 'Nhập hàng', exact: true }))
  await screen.findByRole('heading', { level: 3, name: 'Phiếu nhập hàng' })
  expect(screen.queryByRole('button', { name: 'Nhà cung cấp', exact: true })?.getAttribute('aria-current')).not.toBe('page')
  await act(() => router.navigate('/admin/purchases?tab=1'))
  expect(await screen.findByRole('heading', { level: 3, name: 'Phiếu nhập hàng' })).toBeInTheDocument()
  await act(() => router.navigate('/admin/inventory?tab=low-stock'))
  expect(await screen.findByRole('heading', { level: 3, name: 'Sắp hết hàng' })).toBeInTheDocument()
})

test('missing suppliers:view blocks the route without reading any supplier data', async () => {
  renderPage('/admin/suppliers', ['admin.portal', 'inventory:view'], adminRoutes)
  await screen.findByText('Không có quyền truy cập')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/suppliers'))).toBe(false)
})
