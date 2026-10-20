import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'
import PurchasesPage from './PurchasesPage.jsx'
import PurchaseDetailPageRoute from './PurchaseDetailPageRoute.jsx'
import PurchaseFormPageRoute from './PurchaseFormPageRoute.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), createPurchase: vi.fn(), updatePurchase: vi.fn(), addPurchaseItem: vi.fn(), updatePurchaseItem: vi.fn(), removePurchaseItem: vi.fn(), decidePurchase: vi.fn(), deletePurchase: vi.fn(), receivePurchase: vi.fn(), closePurchase: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/purchases.js', async (original) => ({ ...await original(), ...Object.fromEntries(Object.entries(api).filter(([key]) => key !== 'getAdminData')) }))

const permissions = ['admin.portal', 'purchases:view', 'purchases:create', 'purchases:update', 'purchases:delete', 'purchases:export', 'purchase_history:view', 'suppliers:view', 'products:view']
const supplier = { SupplierId: 's1', Name: 'NCC từ API', IsActive: true }
const variant = { ProductVariantId: 'v1', ProductId: 'p1', Name: 'Điện thoại', Sku: 'PHONE-DEN', VariantName: 'Đen', CostPrice: '1500000.00', IsSerialTracked: true, IsDeleted: false }
const base = { PurchaseOrderId: 'po1', PurchaseOrderCode: 'PN-THAT-01', SupplierId: 's1', CreatedByUserId: 'creator1', CreatedByName: 'Nhân viên lập phiếu', TotalAmount: '3000000.00', Status: 'Pending', Note: 'Ghi chú phiếu thật', CreatedAt: '2026-10-13T17:30:00Z', Items: [{ PurchaseOrderItemId: 'i1', ProductVariantId: 'v1', OrderedQuantity: 2, ReceivedQuantity: 0, UnitPrice: '1500000.00', LineTotal: '3000000.00', Note: null }] }
let orders, variants, suppliers, receipts

function renderPage(path = '/admin/purchases', granted = permissions, role = 'Admin', routes) {
  const router = createMemoryRouter(routes ?? [{ path: '/admin/purchases', element: <PurchasesPage /> }, { path: '/admin/purchases/:purchaseId', element: <PurchaseDetailPageRoute /> }, { path: '/admin/purchases/new', element: <PurchaseFormPageRoute /> }, { path: '/admin/purchases/:purchaseId/edit', element: <PurchaseFormPageRoute /> }], { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
function update(id, body) { orders = orders.map((po) => po.PurchaseOrderId === id ? { ...po, ...body } : po); return structuredClone(orders.find((po) => po.PurchaseOrderId === id)) }
function page(rows, query) { return { Items: structuredClone(rows.slice((query.page - 1) * query.page_size, query.page * query.page_size)), Total: rows.length } }

beforeEach(() => {
  vi.resetAllMocks()
  orders = []; variants = [variant]; suppliers = [supplier]; receipts = []
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/purchase-orders') return page(orders, query)
    if (path === '/admin/suppliers') return page(suppliers, query)
    if (path === '/admin/variants') return page(variants, query)
    if (path === '/admin/variants/v1') return structuredClone(variant)
    if (path === '/admin/products/p1') return { ProductId: 'p1', Name: 'Điện thoại' }
    if (path.endsWith('/receipts')) return structuredClone(receipts)
    if (path.startsWith('/admin/users/')) throw new Error('Không được gọi API tài khoản trong phiên này.')
    const found = orders.find((po) => path === '/admin/purchase-orders/' + po.PurchaseOrderId)
    if (found) return structuredClone(found)
    throw new Error('Không tìm thấy dữ liệu.')
  })
  api.createPurchase.mockImplementation(async (_, body) => { const saved = { ...base, ...body, PurchaseOrderCode: 'PN-NEW', PurchaseOrderId: 'po-new', Status: 'Approved', Items: body.Items.map((item, index) => ({ ...item, PurchaseOrderItemId: 'new-' + index, ReceivedQuantity: 0, LineTotal: String(Number(item.UnitPrice) * item.OrderedQuantity) })) }; orders.push(saved); return saved })
  api.updatePurchase.mockImplementation(async (_, id, body) => {
    const po = orders.find((row) => row.PurchaseOrderId === id)
    return update(id, { ...body, ...(body.Items ? { Items: body.Items.map((line) => ({ ...po.Items.find((item) => item.ProductVariantId === line.ProductVariantId), ...line, LineTotal: String(line.OrderedQuantity * Number(line.UnitPrice)) })) } : {}) })
  })
  api.updatePurchaseItem.mockImplementation(async (_, id, itemId, body) => update(id, { Items: orders.find((po) => po.PurchaseOrderId === id).Items.map((item) => item.PurchaseOrderItemId === itemId ? { ...item, ...body } : item) }))
  api.decidePurchase.mockImplementation(async (_, id, body) => update(id, body))
  api.deletePurchase.mockImplementation(async (_, id) => { orders = orders.filter((po) => po.PurchaseOrderId !== id) })
  api.closePurchase.mockImplementation(async (_, id, body) => update(id, { Status: 'Closed', CloseReason: body.Reason }))
  api.receivePurchase.mockImplementation(async (_, id, body) => {
    const po = orders.find((row) => row.PurchaseOrderId === id)
    const items = po.Items.map((item) => ({ ...item, ReceivedQuantity: item.ReceivedQuantity + (body.Items.find((line) => line.PurchaseOrderItemId === item.PurchaseOrderItemId)?.Quantity ?? 0) }))
    receipts.push({ PurchaseReceiptId: 'r' + receipts.length, ReceivedAt: '2026-10-14T02:00:00Z', Note: body.Note, Items: body.Items.map((item) => ({ ...item, UnitPrice: '1500000.00' })) })
    return update(id, { Items: items, Status: items.every((item) => item.ReceivedQuantity === item.OrderedQuantity) ? 'Completed' : 'Receiving' })
  })
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

test('empty state retains all eight Figma columns and zero count without sample records', async () => {
  renderPage()
  await screen.findByText('Chưa có phiếu nhập.')
  for (const name of ['Mã phiếu', 'Nhà cung cấp', 'Người tạo', 'Ngày lập', 'Tổng SL', 'Tổng tiền', 'Trạng thái', 'Thao tác']) expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
  expect(screen.getByText('0 phiếu')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 phiếu')).toBeInTheDocument()
  expect(screen.queryByText('PN-202610-018')).not.toBeInTheDocument()
})

test('server creator name works for Staff without account permissions and quantities come from actual item lines', async () => {
  orders = [structuredClone(base)]
  renderPage('/admin/purchases', permissions.filter((p) => !p.endsWith(':export')), 'Staff')
  await screen.findByText('Nhân viên lập phiếu')
  const row = within(screen.getByRole('table')).getAllByRole('row')[1]
  expect(row).toHaveTextContent('NCC từ API')
  expect(row).toHaveTextContent('14/10/2026')
  expect(within(row).getByText('2')).toBeInTheDocument()
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/users'))).toBe(false)
})

test('search, supplier, parent product and inclusive dates combine across every loaded purchase page', async () => {
  orders = Array.from({ length: 101 }, (_, index) => ({ ...structuredClone(base), PurchaseOrderId: 'bulk-' + index, PurchaseOrderCode: 'PN-' + index, SupplierId: index === 100 ? 's1' : 's2' }))
  const router = renderPage('/admin/purchases?page=2')
  await screen.findByText('101 phiếu')
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'dien thoai' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Nhà cung cấp' }), { target: { value: 's1' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Sản phẩm' }), { target: { value: 'p1' } })
  fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2026-10-14' } })
  fireEvent.change(screen.getByLabelText('Đến ngày'), { target: { value: '2026-10-14' } })
  expect(screen.queryByRole('button', { name: 'Tìm kiếm', exact: true })).not.toBeInTheDocument()
  await screen.findByText('1 phiếu')
  expect(screen.getByText('PN-100')).toBeInTheDocument()
  expect(router.state.location.search).not.toContain('page=')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/purchase-orders', { page: 2, page_size: 100 }, expect.any(AbortSignal))
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  await screen.findByText('101 phiếu')
  expect(screen.getByRole('searchbox')).toHaveValue('')
})

test('history status and pagination include all processed states and URL history restores filters', async () => {
  orders = ['Pending', 'Approved', 'Rejected', 'Receiving', 'Completed', 'Closed', 'Cancelled'].map((Status, index) => ({ ...structuredClone(base), Status, PurchaseOrderId: 'po' + index, PurchaseOrderCode: 'PN-' + index }))
  const router = renderPage('/admin/purchases?page=99')
  await waitFor(() => expect(router.state.location.search).toBe('?page=2'))
  await screen.findByText('Hiển thị 6–7 trong 7 phiếu')
  fireEvent.click(screen.getByRole('button', { name: 'Lịch sử đã xử lý' }))
  await screen.findByText('6 phiếu')
  fireEvent.click(screen.getByRole('button', { name: 'Từ chối', exact: true }))
  await screen.findByText('1 phiếu')
  await act(() => router.navigate(-1))
  await screen.findByText('6 phiếu')
})

test('export downloads every filtered row rather than only the visible page', async () => {
  orders = Array.from({ length: 7 }, (_, index) => ({ ...structuredClone(base), PurchaseOrderId: 'po' + index, PurchaseOrderCode: 'PN-' + index }))
  const createObjectURL = vi.fn(() => 'blob:report'), revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = revokeObjectURL })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  renderPage()
  await screen.findByText('7 phiếu')
  fireEvent.click(screen.getByRole('button', { name: 'Xuất báo cáo' }))
  expect(click).toHaveBeenCalledTimes(1)
  const blob = createObjectURL.mock.calls[0][0]
  const content = await new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(blob) })
  expect(content).toContain('PN-6')
  expect(content.split('\r\n')).toHaveLength(8)
})

test('creation sends only chosen variants and leaves code, status, creator, totals and received quantity to the server', async () => {
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Tạo phiếu nhập' }))
  const form = await screen.findByRole('form', { name: 'Tạo phiếu nhập' })
  await waitFor(() => expect(within(form).getByRole('button', { name: 'Lưu phiếu' })).toBeEnabled())
  fireEvent.change(within(form).getByRole('combobox', { name: 'Nhà cung cấp' }), { target: { value: 's1' } })
  fireEvent.change(within(form).getByRole('combobox', { name: 'Sản phẩm / biến thể dòng 1' }), { target: { value: 'v1' } })
  expect(within(form).getByRole('spinbutton', { name: 'Đơn giá nhập dòng 1' })).toHaveValue(null)
  fireEvent.change(within(form).getByRole('spinbutton', { name: 'Số lượng đặt dòng 1' }), { target: { value: '3' } })
  fireEvent.change(within(form).getByRole('spinbutton', { name: 'Đơn giá nhập dòng 1' }), { target: { value: '1500000.00' } })
  fireEvent.click(within(form).getByRole('button', { name: 'Lưu phiếu' }))
  await waitFor(() => expect(api.createPurchase).toHaveBeenCalledWith('access-for-test', { SupplierId: 's1', Note: null, Items: [{ ProductVariantId: 'v1', OrderedQuantity: 3, UnitPrice: '1500000.00', Note: null }] }))
  await screen.findByText('Phiếu nhập PN-NEW')
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

test('editing sends the header and full desired lines atomically, never sending received quantities', async () => {
  orders = [{ ...structuredClone(base), CreatedByUserId: 'Admin-id' }]
  renderPage('/admin/purchases?dialog=edit&purchase=po1')
  const form = await screen.findByRole('form', { name: 'Sửa phiếu nhập' })
  const note = within(form).getByRole('textbox', { name: 'Ghi chú phiếu' })
  fireEvent.change(note, { target: { value: '' } })
  const quantity = within(form).getByRole('spinbutton', { name: 'Số lượng đặt dòng 1' })
  fireEvent.change(quantity, { target: { value: '4' } })
  await waitFor(() => expect(within(form).getByRole('button', { name: 'Cập nhật phiếu' })).toBeEnabled())
  fireEvent.click(within(form).getByRole('button', { name: 'Cập nhật phiếu' }))
  await waitFor(() => expect(api.updatePurchase).toHaveBeenCalledExactlyOnceWith('access-for-test', 'po1', { SupplierId: 's1', Note: null, Items: [
    { ProductVariantId: 'v1', OrderedQuantity: 4, UnitPrice: '1500000.00', Note: null },
  ] }))
  expect(api.updatePurchaseItem).not.toHaveBeenCalled()
})

test('fresh approved detail blocks editing even if a stale list originally showed Pending', async () => {
  orders = [{ ...structuredClone(base), Status: 'Approved' }]
  renderPage('/admin/purchases?dialog=edit&purchase=po1')
  await screen.findByText(/không còn được phép sửa/)
  expect(screen.queryByRole('form')).not.toBeInTheDocument()
  expect(api.updatePurchase).not.toHaveBeenCalled()
})

test.each([['approve', 'Duyệt phiếu', { Status: 'Approved' }], ['reject', 'Từ chối phiếu', { Status: 'Rejected', RejectReason: 'Sai giá nhập' }]])('Admin %s requires explicit confirmation and rejection reason where applicable', async (action, label, body) => {
  orders = [structuredClone(base)]
  renderPage('/admin/purchases?dialog=view&purchase=po1')
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(await within(dialog).findByRole('button', { name: label }))
  const confirmation = screen.getByRole('dialog')
  const confirmLabel = action === 'reject' ? 'Xác nhận từ chối' : 'Xác nhận phiếu'
  expect(api.decidePurchase).not.toHaveBeenCalled()
  if (action === 'reject') {
    expect(within(confirmation).getByRole('button', { name: confirmLabel })).toBeDisabled()
    fireEvent.change(within(confirmation).getByRole('textbox', { name: 'Lý do từ chối' }), { target: { value: 'Sai giá nhập' } })
  }
  fireEvent.click(within(confirmation).getByRole('button', { name: confirmLabel }))
  await waitFor(() => expect(api.decidePurchase).toHaveBeenCalledWith('access-for-test', 'po1', body))
})

test('Admin cannot approve its own pending order; Staff cannot approve or close shortages', async () => {
  orders = [{ ...structuredClone(base), CreatedByUserId: 'Admin-id' }]
  renderPage('/admin/purchases?dialog=view&purchase=po1')
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Ghi chú phiếu thật')
  expect(within(dialog).queryByRole('button', { name: /Duyệt phiếu|Từ chối phiếu/ })).not.toBeInTheDocument()
})

test('Staff cannot edit or reopen their rejected purchase', async () => {
  orders = [{ ...structuredClone(base), CreatedByUserId: 'Staff-id', Status: 'Rejected', RejectReason: 'Sai giá' }]
  renderPage('/admin/purchases?dialog=view&purchase=po1', permissions, 'Staff')
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Sai giá')
  expect(within(dialog).queryByRole('button', { name: 'Gửi lại để duyệt' })).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: /Duyệt phiếu|Từ chối phiếu|Đóng phiếu nhận thiếu/ })).not.toBeInTheDocument()
})

test('actual receiving requires real serials and records a partial receipt without changing the ordered quantity', async () => {
  orders = [{ ...structuredClone(base), Status: 'Approved' }]
  renderPage('/admin/purchases?dialog=view&purchase=po1')
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Nhận hàng vào kho' }))
  fireEvent.change(within(dialog).getByRole('spinbutton', { name: 'Số lượng thực nhận PHONE-DEN' }), { target: { value: '1' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận thực nhận' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('đúng một Serial/IMEI')
  expect(api.receivePurchase).not.toHaveBeenCalled()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Serial/IMEI PHONE-DEN' }), { target: { value: 'SN-THAT' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận thực nhận' }))
  await waitFor(() => expect(api.receivePurchase).toHaveBeenCalledWith('access-for-test', 'po1', { Items: [{ PurchaseOrderItemId: 'i1', Quantity: 1, SerialNumbers: ['SN-THAT'] }], Note: null }))
  expect(orders[0].Items[0].OrderedQuantity).toBe(2)
  await within(dialog).findByText('14/10/2026', { exact: false })
  expect(orders[0].Status).toBe('Receiving')
})

test('closing a shortage requires a reason and preserves actual received and missing quantities', async () => {
  orders = [{ ...structuredClone(base), Status: 'Receiving', Items: [{ ...base.Items[0], ReceivedQuantity: 1 }] }]
  renderPage('/admin/purchases?dialog=view&purchase=po1')
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Đóng phiếu nhận thiếu' }))
  expect(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })).toBeDisabled()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Lý do' }), { target: { value: 'NCC không giao tiếp' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true }))
  await waitFor(() => expect(api.closePurchase).toHaveBeenCalledWith('access-for-test', 'po1', { Reason: 'NCC không giao tiếp' }))
  expect(orders[0].Items[0]).toMatchObject({ OrderedQuantity: 2, ReceivedQuantity: 1 })
})

test('trash deletes the document through the API and removes it from the list', async () => {
  orders = [structuredClone(base)]
  const router = renderPage('/admin/purchases?status=Pending')
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa PN-THAT-01' }))
  const dialog = screen.getByRole('dialog', { name: 'Xóa phiếu nhập?' })
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Xác nhận xóa' })).toBeEnabled())
  expect(within(dialog).getByText(/xóa vĩnh viễn/)).toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  await waitFor(() => expect(api.deletePurchase).toHaveBeenCalledWith('access-for-test', 'po1'))
  await screen.findByText('Không có phiếu nhập phù hợp.')
  expect(orders).toHaveLength(0)
  expect(router.state.location.search).toBe('?status=Pending')
})

test('Staff with stale deletion permission sees no trash and cannot open deletion via URL', async () => {
  orders = [structuredClone(base)]
  renderPage('/admin/purchases?dialog=delete&purchase=po1', permissions, 'Staff')
  await screen.findByText('1 phiếu')
  expect(screen.queryByRole('button', { name: 'Xóa PN-THAT-01' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Hủy phiếu' })).not.toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Sửa PN-THAT-01' })).toBeDisabled()
  expect(api.deletePurchase).not.toHaveBeenCalled()
})

test('Admin can delete a fully received purchase', async () => {
  orders = [{ ...structuredClone(base), Status: 'Completed', Items: base.Items.map((item) => ({ ...item, ReceivedQuantity: item.OrderedQuantity })) }]
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa PN-THAT-01' }))
  const dialog = await screen.findByRole('dialog', { name: 'Xóa phiếu nhập?' })
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Xác nhận xóa' })).toBeEnabled())
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  await screen.findByText('Chưa có phiếu nhập.')
  expect(orders).toHaveLength(0)
})

test('failed writes retain typed data, disable repeated pending submissions and block modal dismissal', async () => {
  orders = [structuredClone(base)]
  api.decidePurchase.mockRejectedValueOnce(new Error('Phiếu vừa thay đổi.'))
  renderPage('/admin/purchases?dialog=view&purchase=po1')
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Từ chối phiếu' }))
  const confirmation = screen.getByRole('dialog')
  const reason = within(confirmation).getByRole('textbox', { name: 'Lý do từ chối' })
  fireEvent.change(reason, { target: { value: 'Giữ lý do' } })
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Xác nhận từ chối' }))
  expect(await within(confirmation).findByRole('alert')).toHaveTextContent('Phiếu vừa thay đổi.')
  expect(reason).toHaveValue('Giữ lý do')
  let finish
  api.decidePurchase.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Xác nhận từ chối' }))
  expect(within(confirmation).getByRole('button', { name: 'Hủy', exact: true })).toBeDisabled()
  fireEvent.submit(reason.closest('form'))
  expect(api.decidePurchase).toHaveBeenCalledTimes(2)
  await act(async () => finish({ ...base, Status: 'Rejected', RejectReason: 'Giữ lý do' }))
})

test('read errors remain distinct from an empty directory and can retry', async () => {
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((token, path, query) => path === '/admin/purchase-orders' && failed ? Promise.reject(new Error('Lỗi kết nối.')) : original(token, path, query))
  renderPage()
  await screen.findByText('Lỗi kết nối.')
  expect(screen.queryByText('0 phiếu')).not.toBeInTheDocument()
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Chưa có phiếu nhập.')
})

test('view-only sessions cannot access create/edit/cancel dialogs via direct URLs', async () => {
  orders = [structuredClone(base)]
  const router = renderPage('/admin/purchases?dialog=new', ['admin.portal', 'purchases:view', 'suppliers:view', 'products:view'], 'Staff')
  await screen.findByText('1 phiếu')
  for (const mode of ['new', 'edit', 'delete']) {
    await act(() => router.navigate('/admin/purchases?dialog=' + mode + '&purchase=po1'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: /Tạo phiếu|Xuất báo cáo|Sửa PN|Xóa PN/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Chi tiết PN-THAT-01' }))
  await screen.findByText('Ghi chú phiếu thật')
  expect(router.state.location.pathname).toBe('/admin/purchases/po1')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Xác nhận phiếu|Hủy phiếu/ })).not.toBeInTheDocument()
})

test('actual menu route has the requested header and breadcrumb; suppliers remain separate', async () => {
  renderPage('/admin/purchases', [...permissions, 'orders:view'], 'Admin', adminRoutes)
  await screen.findByRole('heading', { level: 1, name: 'Quản lý nhập hàng' })
  expect(within(screen.getByRole('banner')).getByText('/ Danh sách phiếu nhập')).toBeInTheDocument()
  expect(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Nhập hàng', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('button', { name: 'Nhà cung cấp', exact: true })).not.toHaveAttribute('aria-expanded')
})

test('ungranted purchases:view blocks the route before purchase reads', async () => {
  renderPage('/admin/purchases', ['admin.portal'], 'Staff', adminRoutes)
  await screen.findByText('Không có quyền truy cập')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/purchase-orders'))).toBe(false)
})

test('historical variants hidden from the current catalog are resolved for product search and quantity display', async () => {
  orders = [{ ...structuredClone(base), Status: 'Completed' }]
  variants = []
  const original = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation((token, path, query) => path === '/admin/variants/v1' ? Promise.resolve({ ...variant, IsDeleted: true }) : path === '/admin/products/p1' ? Promise.resolve({ ProductId: 'p1', Name: 'Điện thoại' }) : original(token, path, query))
  renderPage('/admin/purchases?keyword=dien+thoai&product=p1')
  await screen.findByText('1 phiếu')
  expect(screen.getByText('PN-THAT-01')).toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/variants/v1', {}, expect.any(AbortSignal))
})

test('Staff receiving a partial order cannot close its shortage even with update permission', async () => {
  orders = [{ ...structuredClone(base), Status: 'Receiving', Items: [{ ...base.Items[0], ReceivedQuantity: 1 }] }]
  renderPage('/admin/purchases?dialog=view&purchase=po1', permissions, 'Staff')
  const dialog = await screen.findByRole('dialog')
  expect(await within(dialog).findByRole('button', { name: 'Nhận hàng vào kho' })).toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: 'Đóng phiếu nhận thiếu' })).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: 'Hủy phiếu' })).not.toBeInTheDocument()
})

test('a reversed date range from a direct URL is reported rather than counted as zero purchases', async () => {
  orders = [structuredClone(base)]
  renderPage('/admin/purchases?from=2026-10-15&to=2026-10-14')
  await screen.findByText('Từ ngày không được sau Đến ngày.')
  expect(screen.queryByText('0 phiếu')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Xuất báo cáo' })).toBeDisabled()
})
