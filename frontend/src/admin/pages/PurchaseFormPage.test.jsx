import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { formatDate, formatMoney } from '../../lib/format.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), createPurchase: vi.fn(), updatePurchase: vi.fn(), updatePurchaseItem: vi.fn(), addPurchaseItem: vi.fn(), removePurchaseItem: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/purchases.js', async (original) => ({ ...await original(), ...Object.fromEntries(Object.entries(api).filter(([key]) => key !== 'getAdminData')) }))
const permissions = ['admin.portal', 'purchases:view', 'purchases:create', 'purchases:update', 'suppliers:view', 'products:view']
const variants = [
  { ProductVariantId: 'v1', ProductId: 'p1', Name: 'Điện thoại', VariantName: 'Đen', Sku: 'PHONE-DEN', CostPrice: '999.00', IsSerialTracked: true },
  { ProductVariantId: 'v2', ProductId: 'p1', Name: 'Điện thoại', VariantName: 'Trắng', Sku: 'PHONE-TRANG', CostPrice: '888.00', IsSerialTracked: false },
]
const base = { PurchaseOrderId: 'po1', PurchaseOrderCode: 'PN-API-01', SupplierId: 's1', CreatedByUserId: 'staff1', CreatedByName: 'Nhân viên', CreatedAt: '2026-10-12T17:30:00Z', TotalAmount: '2500.00', Status: 'Pending', Note: 'Ghi chú cũ', Items: [{ PurchaseOrderItemId: 'i1', ProductVariantId: 'v1', OrderedQuantity: 2, ReceivedQuantity: 0, UnitPrice: '1250.00', LineTotal: '2500.00', Note: null }] }
let po, suppliers
function renderPage(path = '/admin/purchases/new', granted = permissions, role = 'Admin') {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
function fillLine(index, id, quantity, price) {
  fireEvent.change(screen.getByRole('combobox', { name: 'Sản phẩm / biến thể dòng ' + index }), { target: { value: id } })
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Số lượng đặt dòng ' + index }), { target: { value: String(quantity) } })
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Đơn giá nhập dòng ' + index }), { target: { value: String(price) } })
}
beforeEach(() => {
  vi.resetAllMocks(); po = structuredClone(base); suppliers = [{ SupplierId: 's1', Name: 'NCC hoạt động', IsActive: true }, { SupplierId: 'hidden', Name: 'NCC ẩn', IsActive: false }]
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/purchase-orders/po1') return structuredClone(po)
    if (path === '/admin/purchase-orders') return { Items: [structuredClone(po)], Total: 1 }
    if (path === '/admin/variants') return { Items: structuredClone(variants), Total: variants.length }
    if (path.startsWith('/admin/variants/')) return structuredClone(variants.find((variant) => path.endsWith('/' + variant.ProductVariantId)))
    if (path === '/admin/products/p1') return { ProductId: 'p1', Name: 'Điện thoại' }
    if (path === '/admin/suppliers') return { Items: structuredClone(suppliers), Total: suppliers.length }
    throw new Error('Không tìm thấy phiếu nhập.')
  })
  api.createPurchase.mockImplementation(async (_, body) => { po = { ...base, ...body, Status: 'Approved', CreatedAt: '2026-10-14T06:00:00Z', Items: body.Items.map((item, index) => ({ ...item, PurchaseOrderItemId: 'i' + (index + 1), ReceivedQuantity: 0, LineTotal: String(item.OrderedQuantity * Number(item.UnitPrice)) })) }; return structuredClone(po) })
  api.updatePurchase.mockImplementation(async (_, __, body) => { po = { ...po, ...body }; return structuredClone(po) })
  api.updatePurchaseItem.mockImplementation(async (_, __, id, body) => { po.Items = po.Items.map((item) => item.PurchaseOrderItemId === id ? { ...item, ...body, LineTotal: String((body.OrderedQuantity ?? item.OrderedQuantity) * Number(body.UnitPrice ?? item.UnitPrice)) } : item); return structuredClone(po) })
  api.addPurchaseItem.mockImplementation(async (_, __, body) => { po.Items.push({ ...body, PurchaseOrderItemId: 'i-new', ReceivedQuantity: 0, LineTotal: String(body.OrderedQuantity * Number(body.UnitPrice)) }); return structuredClone(po) })
  api.removePurchaseItem.mockImplementation(async (_, __, id) => { po.Items = po.Items.filter((item) => item.PurchaseOrderItemId !== id); return structuredClone(po) })
})

test('new route matches Figma sections, keeps automatic code/date readonly and removes the received column', async () => {
  renderPage()
  await screen.findByRole('form', { name: 'Tạo phiếu nhập' })
  expect(screen.getByRole('heading', { level: 1, name: 'Tạo phiếu nhập' })).toBeInTheDocument()
  expect(within(screen.getByRole('banner')).getByText('/ Tạo phiếu nhập')).toBeInTheDocument()
  expect(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Nhập hàng', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('textbox', { name: 'Mã phiếu' })).toHaveValue('Tự động tạo sau khi lưu')
  expect(screen.getByRole('textbox', { name: 'Mã phiếu' })).toHaveAttribute('readonly')
  expect(screen.getByRole('textbox', { name: 'Ngày lập' })).toHaveValue(formatDate(new Date()))
  expect(screen.getByRole('textbox', { name: 'Ngày lập' })).toHaveAttribute('readonly')
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Sản phẩm / biến thể', 'SL đặt', 'Đơn giá nhập', 'Thành tiền', 'Thao tác'])
  expect(screen.queryByText(/SL thực nhận/)).not.toBeInTheDocument()
  expect(screen.getByRole('status', { name: 'Tổng tiền phiếu nhập' }).textContent).toBe(formatMoney('0.00'))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('selected variants keep manually entered prices and each row/total recalculates immediately', async () => {
  renderPage()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Lưu phiếu' })).toBeEnabled())
  fireEvent.change(screen.getByRole('combobox', { name: 'Sản phẩm / biến thể dòng 1' }), { target: { value: 'v1' } })
  expect(screen.getByRole('spinbutton', { name: 'Đơn giá nhập dòng 1' })).toHaveValue(null)
  fillLine(1, 'v1', 3, 1250)
  fillLine(2, 'v2', 2, 2500)
  expect(screen.getByRole('status', { name: 'Thành tiền dòng 1' }).textContent).toBe(formatMoney('3750.00'))
  expect(screen.getByRole('status', { name: 'Tổng tiền phiếu nhập' }).textContent).toBe(formatMoney('8750.00'))
  fireEvent.click(screen.getByRole('button', { name: 'Xóa dòng 2' }))
  expect(screen.getByRole('status', { name: 'Tổng tiền phiếu nhập' }).textContent).toBe(formatMoney('3750.00'))
  expect(screen.getByRole('button', { name: 'Xóa dòng 1' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '+ Thêm sản phẩm' }))
  expect(screen.getAllByRole('combobox', { name: /Sản phẩm \/ biến thể dòng/ })).toHaveLength(2)
})

test('supplier choices use active records, duplicate SKU choices are disabled and writes wait until save', async () => {
  renderPage()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Lưu phiếu' })).toBeEnabled())
  expect(within(screen.getByRole('combobox', { name: 'Nhà cung cấp' })).queryByRole('option', { name: 'NCC ẩn' })).not.toBeInTheDocument()
  fillLine(1, 'v1', 2, 1250)
  expect(within(screen.getByRole('combobox', { name: 'Sản phẩm / biến thể dòng 2' })).getByRole('option', { name: 'Điện thoại / Đen / PHONE-DEN' })).toBeDisabled()
  expect(api.createPurchase).not.toHaveBeenCalled()
  expect(api.addPurchaseItem).not.toHaveBeenCalled()
})

test('saving a new order submits entered unit prices only and opens its detail using the server date and status', async () => {
  const router = renderPage('/admin/purchases/new?status=Pending')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Lưu phiếu' })).toBeEnabled())
  fireEvent.change(screen.getByRole('combobox', { name: 'Nhà cung cấp' }), { target: { value: 's1' } })
  fillLine(1, 'v1', 3, '12.50')
  fireEvent.change(screen.getByRole('textbox', { name: 'Ghi chú phiếu' }), { target: { value: ' ghi chú tự nhập ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu phiếu' }))
  await waitFor(() => expect(api.createPurchase).toHaveBeenCalledWith('access-for-test', { SupplierId: 's1', Note: 'ghi chú tự nhập', Items: [{ ProductVariantId: 'v1', OrderedQuantity: 3, UnitPrice: '12.50', Note: null }] }))
  await screen.findByRole('heading', { name: 'Phiếu nhập PN-API-01' })
  expect(router.state.location.pathname).toBe('/admin/purchases/po1')
  expect(router.state.location.search).toBe('?status=Pending')
  expect(screen.getByText('Đã tạo phiếu nhập.')).toBeInTheDocument()
  expect(screen.getByText('13:00 14/10/2026')).toBeInTheDocument()
})

test('edit uses the stored date; removing/replacing variants stays in the draft until the single update action', async () => {
  const router = renderPage('/admin/purchases/po1/edit')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Cập nhật phiếu' })).toBeEnabled())
  expect(screen.getByRole('textbox', { name: 'Ngày lập' })).toHaveValue('13/10/2026')
  expect(screen.getByRole('textbox', { name: 'Mã phiếu' })).toHaveValue('PN-API-01')
  fillLine(1, 'v2', 1, 3200)
  expect(api.addPurchaseItem).not.toHaveBeenCalled()
  expect(api.removePurchaseItem).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Cập nhật phiếu' }))
  await screen.findByText('Đã cập nhật phiếu nhập.')
  expect(router.state.location.pathname).toBe('/admin/purchases/po1')
  expect(api.addPurchaseItem).toHaveBeenCalledWith('access-for-test', 'po1', { ProductVariantId: 'v2', OrderedQuantity: 1, UnitPrice: '3200', Note: null })
  expect(api.removePurchaseItem).toHaveBeenCalledWith('access-for-test', 'po1', 'i1')
  expect(api.updatePurchase).not.toHaveBeenCalled()
  expect(po.CreatedAt).toBe(base.CreatedAt)
})

test('failed create retains the complete draft and blocks repeat submission and navigation controls while retry is pending', async () => {
  api.createPurchase.mockRejectedValueOnce(new Error('Lỗi kết nối.'))
  renderPage()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Lưu phiếu' })).toBeEnabled())
  fireEvent.change(screen.getByRole('combobox', { name: 'Nhà cung cấp' }), { target: { value: 's1' } })
  fillLine(1, 'v1', 2, 1250)
  fireEvent.click(screen.getByRole('button', { name: 'Lưu phiếu' }))
  await screen.findByText('Lỗi kết nối.')
  expect(screen.getByRole('spinbutton', { name: 'Đơn giá nhập dòng 1' })).toHaveValue(1250)
  let finish
  api.createPurchase.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  fireEvent.click(screen.getByRole('button', { name: 'Lưu phiếu' }))
  expect(screen.getByRole('button', { name: 'Hủy', exact: true })).toBeDisabled()
  expect(screen.getByRole('button', { name: '← Danh sách phiếu nhập' })).toBeDisabled()
  fireEvent.submit(screen.getByRole('form', { name: 'Tạo phiếu nhập' }))
  expect(api.createPurchase).toHaveBeenCalledTimes(2)
  await act(async () => finish(structuredClone(po)))
})

test.each([['/admin/purchases/new', 'purchases:create'], ['/admin/purchases/po1/edit', 'purchases:update']])('missing %s permission blocks the route before domain data reads', async (path, denied) => {
  renderPage(path, permissions.filter((permission) => permission !== denied))
  await screen.findByText('Không có quyền truy cập')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/'))).toBe(false)
})

test('metadata read errors disable saving, allow retry and do not clear entered notes', async () => {
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/variants' && failed ? Promise.reject(new Error('Lỗi tải sản phẩm.')) : original(...args))
  renderPage()
  await screen.findByText('Lỗi tải sản phẩm.')
  fireEvent.change(screen.getByRole('textbox', { name: 'Ghi chú phiếu' }), { target: { value: 'Giữ ghi chú' } })
  expect(screen.getByRole('button', { name: 'Lưu phiếu' })).toBeDisabled()
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Lưu phiếu' })).toBeEnabled())
  expect(screen.getByRole('textbox', { name: 'Ghi chú phiếu' })).toHaveValue('Giữ ghi chú')
})

test('cancel discards local edits, returns to the detail and never cancels the actual purchase', async () => {
  const router = renderPage('/admin/purchases/po1/edit?keyword=PN-API&status=Pending')
  await screen.findByRole('form', { name: 'Sửa phiếu nhập' })
  fireEvent.change(screen.getByRole('textbox', { name: 'Ghi chú phiếu' }), { target: { value: 'Chưa lưu' } })
  fireEvent.click(screen.getByRole('button', { name: 'Hủy', exact: true }))
  await screen.findByRole('heading', { name: 'Phiếu nhập PN-API-01' })
  expect(router.state.location.pathname).toBe('/admin/purchases/po1')
  expect(router.state.location.search).toContain('status=Pending')
  expect(po.Note).toBe('Ghi chú cũ')
  expect(api.updatePurchase).not.toHaveBeenCalled()
})

test('a hidden supplier already linked to the order stays visible without allowing selection on a new order', async () => {
  po.SupplierId = 'hidden'
  renderPage('/admin/purchases/po1/edit')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Cập nhật phiếu' })).toBeEnabled())
  expect(screen.getByRole('combobox', { name: 'Nhà cung cấp' })).toHaveValue('hidden')
  expect(screen.getByRole('option', { name: 'NCC ẩn (Ẩn)' })).toBeDisabled()
})
