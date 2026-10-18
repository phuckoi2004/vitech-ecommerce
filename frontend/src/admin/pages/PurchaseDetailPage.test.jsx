import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), decidePurchase: vi.fn(), updatePurchase: vi.fn(), updatePurchaseItem: vi.fn(), receivePurchase: vi.fn(), resubmitPurchase: vi.fn(), closePurchase: vi.fn(), cancelPurchase: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/purchases.js', async (original) => ({ ...await original(), ...Object.fromEntries(Object.entries(api).filter(([key]) => key !== 'getAdminData')) }))

const permissions = ['admin.portal', 'purchases:view', 'purchases:update', 'purchases:delete', 'purchase_history:view', 'suppliers:view', 'products:view']
const variants = [
  { ProductVariantId: 'v1', ProductId: 'p1', Sku: 'PHONE-DEN', Name: 'Điện thoại', VariantName: 'Đen', IsSerialTracked: true },
  { ProductVariantId: 'v2', ProductId: 'p1', Sku: 'PHONE-TRANG', Name: 'Điện thoại', VariantName: 'Trắng', IsSerialTracked: false },
]
const base = {
  PurchaseOrderId: 'po1', PurchaseOrderCode: 'PN-API-01', SupplierId: 's1', CreatedByUserId: 'staff1', CreatedByName: 'Tên người lập từ API',
  CreatedAt: '2026-10-13T17:30:00Z', TotalAmount: '5000000.00', Status: 'Pending', Note: 'Ghi chú thật', DecidedByUserId: null, DecidedAt: null, RejectReason: null,
  Items: [
    { PurchaseOrderItemId: 'i1', ProductVariantId: 'v1', OrderedQuantity: 2, ReceivedQuantity: 0, UnitPrice: '1500000.00', LineTotal: '3000000.00', Note: 'Kiểm tra bao bì' },
    { PurchaseOrderItemId: 'i2', ProductVariantId: 'v2', OrderedQuantity: 1, ReceivedQuantity: 0, UnitPrice: '2000000.00', LineTotal: '2000000.00', Note: null },
  ],
}
let po, receipts
function renderPage(path = '/admin/purchases/po1', granted = permissions, role = 'Admin') {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
function save(body) { po = { ...po, ...body }; return structuredClone(po) }
beforeEach(() => {
  vi.resetAllMocks(); po = structuredClone(base); receipts = []
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/purchase-orders/po1') return structuredClone(po)
    if (path === '/admin/purchase-orders') return { Items: [structuredClone(po)], Total: 1 }
    if (path === '/admin/purchase-orders/po1/receipts') return structuredClone(receipts)
    if (path === '/admin/suppliers') return { Items: [{ SupplierId: 's1', Name: 'Nhà cung cấp thật', IsActive: true }], Total: 1 }
    if (path === '/admin/variants') return { Items: structuredClone(variants), Total: variants.length }
    if (path.startsWith('/admin/variants/')) return structuredClone(variants.find((variant) => path.endsWith('/' + variant.ProductVariantId)))
    if (path === '/admin/products/p1') return { ProductId: 'p1', Name: 'Điện thoại' }
    if (path.startsWith('/admin/users/')) return { FullName: 'Admin đã xử lý' }
    throw new Error('Không tìm thấy phiếu nhập.')
  })
  api.decidePurchase.mockImplementation(async (_, __, body) => save({ ...body, DecidedByUserId: 'Admin-id', DecidedAt: '2026-10-14T06:00:00Z' }))
  api.updatePurchase.mockImplementation(async (_, __, body) => save({ ...body, ...(body.Items ? { Items: body.Items.map((line) => ({ ...po.Items.find((item) => item.ProductVariantId === line.ProductVariantId), ...line, LineTotal: String(line.OrderedQuantity * Number(line.UnitPrice)) })) } : {}) }))
  api.updatePurchaseItem.mockImplementation(async (_, __, itemId, body) => save({ Items: po.Items.map((item) => item.PurchaseOrderItemId === itemId ? { ...item, ...body } : item) }))
  api.resubmitPurchase.mockImplementation(async () => save({ Status: 'Pending', DecidedByUserId: null, DecidedAt: null, RejectReason: null }))
  api.closePurchase.mockImplementation(async (_, __, body) => save({ Status: 'Closed', CloseReason: body.Reason, ClosedByUserId: 'Admin-id', ClosedAt: '2026-10-14T06:00:00Z' }))
  api.cancelPurchase.mockImplementation(async () => save({ Status: 'Cancelled' }))
  api.receivePurchase.mockImplementation(async (_, __, body) => {
    const Items = po.Items.map((item) => ({ ...item, ReceivedQuantity: item.ReceivedQuantity + (body.Items.find((line) => line.PurchaseOrderItemId === item.PurchaseOrderItemId)?.Quantity ?? 0) }))
    receipts.push({ PurchaseReceiptId: 'receipt1', ReceivedAt: '2026-10-14T06:00:00Z', Note: 'Biên nhận thật', Items: body.Items.map((item) => ({ ...item, UnitPrice: '1500000.00' })) })
    return save({ Items, Status: Items.every((item) => item.ReceivedQuantity === item.OrderedQuantity) ? 'Completed' : 'Receiving' })
  })
})

test('the file icon opens the separate detail route, keeps filters and returns to the same list', async () => {
  const router = renderPage('/admin/purchases?keyword=PN-API&status=Pending&supplier=s1&product=p1&from=2026-10-14&to=2026-10-14')
  fireEvent.click(await screen.findByRole('button', { name: 'Chi tiết PN-API-01' }))
  await screen.findByRole('heading', { name: 'Phiếu nhập PN-API-01' })
  expect(router.state.location.pathname).toBe('/admin/purchases/po1')
  expect(router.state.location.search).not.toMatch(/dialog|purchase=/)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '← Danh sách phiếu nhập' }))
  await screen.findByRole('heading', { name: 'Danh sách phiếu nhập' })
  expect(router.state.location.search).toContain('status=Pending')
  expect(router.state.location.search).toContain('keyword=PN-API')
  expect(router.state.location.search).toContain('product=p1')
})

test('direct detail URLs render Figma cards, six columns, active menu and current header without loading other purchases', async () => {
  renderPage()
  await screen.findByText('Điện thoại - Đen')
  expect(screen.getByRole('heading', { level: 1, name: 'Chi tiết phiếu nhập' })).toBeInTheDocument()
  expect(within(screen.getByRole('banner')).getByText('/ Chi tiết phiếu nhập')).toBeInTheDocument()
  expect(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Nhập hàng', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(document.title).toBe('Chi tiết phiếu nhập | VieTech')
  for (const title of ['Thông tin phiếu nhập', 'Xử lý của quản trị viên', 'Chi tiết sản phẩm nhập']) expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
  expect(within(screen.getByRole('table')).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Sản phẩm / biến thể', 'SL đặt', 'SL thực nhận', 'Đơn giá nhập', 'Thành tiền', 'Ghi chú'])
  expect(screen.getByText('Điện thoại - Trắng')).toBeInTheDocument()
  expect(screen.getByText('Tên người lập từ API')).toBeInTheDocument()
  expect(screen.getByText('00:30 14/10/2026')).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Lịch sử nhận hàng' })).not.toBeInTheDocument()
  expect(api.getAdminData.mock.calls.some(([, path]) => path === '/admin/purchase-orders')).toBe(false)
  expect(screen.queryByText('PN-202610-018')).not.toBeInTheDocument()
})

test('approval uses the decision API only after confirmation; it never changes inventory or received quantities', async () => {
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận phiếu', exact: true }))
  expect(api.decidePurchase).not.toHaveBeenCalled()
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Xác nhận phiếu', exact: true }))
  await waitFor(() => expect(api.decidePurchase).toHaveBeenCalledWith('access-for-test', 'po1', { Status: 'Approved' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'Sửa phiếu' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Nhận hàng vào kho' })).toBeEnabled()
  expect(po.Items.map((item) => item.ReceivedQuantity)).toEqual([0, 0])
  expect(api.receivePurchase).not.toHaveBeenCalled()
})

test('rejection requires a reason; a failed request keeps it and blocks repeat writes or closing while retry runs', async () => {
  api.decidePurchase.mockRejectedValueOnce(new Error('Phiếu vừa thay đổi.'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Từ chối', exact: true }))
  const dialog = screen.getByRole('dialog')
  expect(within(dialog).getByRole('button', { name: 'Xác nhận từ chối' })).toBeDisabled()
  const input = within(dialog).getByRole('textbox', { name: 'Lý do từ chối' })
  fireEvent.change(input, { target: { value: '  Sai giá nhập  ' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận từ chối' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Phiếu vừa thay đổi.')
  expect(input).toHaveValue('  Sai giá nhập  ')
  let finish
  api.decidePurchase.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận từ chối' }))
  expect(within(dialog).getByRole('button', { name: 'Hủy', exact: true })).toBeDisabled()
  fireEvent.submit(input.closest('form'))
  expect(api.decidePurchase).toHaveBeenCalledTimes(2)
  expect(api.decidePurchase).toHaveBeenLastCalledWith('access-for-test', 'po1', { Status: 'Rejected', RejectReason: 'Sai giá nhập' })
  await act(async () => finish(save({ Status: 'Rejected', RejectReason: 'Sai giá nhập' })))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'Gửi lại để duyệt' })).toBeInTheDocument()
  expect(screen.getByText('Sai giá nhập')).toBeInTheDocument()
})

test.each(['Staff', 'Admin'])('%s cannot approve its own pending order even via a direct action URL', async (role) => {
  po.CreatedByUserId = role + '-id'
  renderPage('/admin/purchases/po1?dialog=approve', permissions, role)
  await screen.findByText('Điện thoại - Đen')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Xác nhận phiếu', exact: true })).not.toBeInTheDocument()
  expect(api.decidePurchase).not.toHaveBeenCalled()
})

test('Staff can read creator names without account API access; an unavailable approver name displays the actual account ID', async () => {
  po = { ...po, Status: 'Approved', DecidedByUserId: 'admin-decider', DecidedAt: '2026-10-14T06:00:00Z' }
  renderPage('/admin/purchases/po1', [...permissions, 'users:read', 'users:manage'], 'Staff')
  await screen.findByText('Điện thoại - Đen')
  expect(screen.getByText('Tên người lập từ API')).toBeInTheDocument()
  expect(screen.getByText('ID: admin-decider')).toBeInTheDocument()
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/users/'))).toBe(false)
  expect(screen.queryByRole('button', { name: 'Từ chối', exact: true })).not.toBeInTheDocument()
})

test('Admin with account permission resolves the approving name using the existing user API', async () => {
  po = { ...po, Status: 'Approved', DecidedByUserId: 'admin-decider', DecidedAt: '2026-10-14T06:00:00Z' }
  renderPage('/admin/purchases/po1', [...permissions, 'users:read', 'users:manage'])
  await screen.findByText('Admin đã xử lý')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/users/admin-decider', { include_deleted: true }, expect.any(AbortSignal))
})

test.each(['Staff', 'Admin'])('%s sees the API approver name without account management access or extra account reads', async (role) => {
  po = { ...po, Status: 'Approved', DecidedByUserId: 'other-admin', DecidedByName: 'Admin duyệt từ API', DecidedAt: '2026-10-14T06:00:00Z' }
  renderPage('/admin/purchases/po1', permissions, role)
  await screen.findByText('Điện thoại - Đen')
  expect(screen.getByText('Người duyệt').nextElementSibling).toHaveTextContent('Admin duyệt từ API')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/users/'))).toBe(false)
})

test('pending order keeps the approver label with an empty value', async () => {
  renderPage()
  await screen.findByText('Điện thoại - Đen')
  expect(screen.getByText('Người duyệt').nextElementSibling).toBeEmptyDOMElement()
})

test.each(['Approved', 'Receiving', 'Completed', 'Closed'])('automatically approved Admin order shows its creator as approver in %s', async (Status) => {
  po = { ...po, Status, CreatedByUserId: 'another-admin', CreatedByName: 'Admin tạo và duyệt', DecidedByUserId: null, DecidedByName: null }
  renderPage()
  await screen.findByText('Điện thoại - Đen')
  expect(screen.getByText('Người duyệt').nextElementSibling).toHaveTextContent('Admin tạo và duyệt')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/users/'))).toBe(false)
})

test.each(['Rejected', 'Cancelled'])('a %s rejected order identifies the rejecting Admin and does not call them an approver', async (Status) => {
  po = { ...po, Status, DecidedByUserId: 'admin-refused', DecidedByName: 'Admin từ chối', RejectReason: 'Sai giá' }
  renderPage()
  await screen.findByText('Điện thoại - Đen')
  expect(screen.getByText('Người duyệt').nextElementSibling).toBeEmptyDOMElement()
  expect(screen.getByText('Người từ chối').nextElementSibling).toHaveTextContent('Admin từ chối')
})

test('editing opens its own page, saves header and lines together and returns to fresh detail', async () => {
  const router = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa phiếu' }))
  const form = await screen.findByRole('form', { name: 'Sửa phiếu nhập' })
  expect(router.state.location.pathname).toBe('/admin/purchases/po1/edit')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  const note = within(form).getByRole('textbox', { name: 'Ghi chú phiếu' })
  fireEvent.change(note, { target: { value: 'Đã sửa ghi chú' } })
  fireEvent.change(within(form).getByRole('spinbutton', { name: 'Số lượng đặt dòng 1' }), { target: { value: '4' } })
  await waitFor(() => expect(within(form).getByRole('button', { name: 'Cập nhật phiếu' })).toBeEnabled())
  fireEvent.click(within(form).getByRole('button', { name: 'Cập nhật phiếu' }))
  await waitFor(() => expect(api.updatePurchase).toHaveBeenCalledExactlyOnceWith('access-for-test', 'po1', { SupplierId: 's1', Note: 'Đã sửa ghi chú', Items: [
    { ProductVariantId: 'v1', OrderedQuantity: 4, UnitPrice: '1500000.00', Note: 'Kiểm tra bao bì' },
    { ProductVariantId: 'v2', OrderedQuantity: 1, UnitPrice: '2000000.00', Note: null },
  ] }))
  expect(api.updatePurchaseItem).not.toHaveBeenCalled()
  await screen.findByText('Đã sửa ghi chú')
  expect(router.state.location.pathname).toBe('/admin/purchases/po1')
  expect(within(screen.getByRole('table')).getByText('4')).toBeInTheDocument()
})

test('partial receipt validates real serials, updates actual quantities and displays only the returned receipt history', async () => {
  po.Status = 'Approved'
  renderPage()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Nhận hàng vào kho' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Nhận hàng vào kho' }))
  const dialog = screen.getByRole('dialog')
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Xác nhận thực nhận' })).toBeEnabled())
  fireEvent.change(within(dialog).getByRole('spinbutton', { name: 'Số lượng thực nhận PHONE-DEN' }), { target: { value: '1' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận thực nhận' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('đúng một Serial/IMEI')
  expect(api.receivePurchase).not.toHaveBeenCalled()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Serial/IMEI PHONE-DEN' }), { target: { value: 'SERIAL-THAT' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận thực nhận' }))
  await waitFor(() => expect(api.receivePurchase).toHaveBeenCalledWith('access-for-test', 'po1', { Items: [{ PurchaseOrderItemId: 'i1', Quantity: 1, SerialNumbers: ['SERIAL-THAT'] }], Note: null }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  await screen.findByText('Biên nhận thật')
  expect(po.Status).toBe('Receiving')
  expect(po.Items[0]).toMatchObject({ OrderedQuantity: 2, ReceivedQuantity: 1 })
  expect(screen.getByRole('button', { name: 'Đóng phiếu nhận thiếu' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Hủy phiếu' })).not.toBeInTheDocument()
})

test('closed shortage keeps the actual quantities and records the reason; Staff cannot close it', async () => {
  po.Status = 'Receiving'; po.Items[0].ReceivedQuantity = 1
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Đóng phiếu nhận thiếu' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Lý do' }), { target: { value: 'NCC giao thiếu' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true }))
  await waitFor(() => expect(api.closePurchase).toHaveBeenCalledWith('access-for-test', 'po1', { Reason: 'NCC giao thiếu' }))
  await screen.findByText('NCC giao thiếu')
  expect(po.Items[0]).toMatchObject({ OrderedQuantity: 2, ReceivedQuantity: 1 })
  expect(screen.queryByRole('button', { name: 'Nhận hàng vào kho' })).not.toBeInTheDocument()
})

test('Staff can resubmit a rejected order but cannot close a partially received order', async () => {
  po.Status = 'Rejected'; po.RejectReason = 'Sai giá'
  const router = renderPage('/admin/purchases/po1', permissions, 'Staff')
  fireEvent.click(await screen.findByRole('button', { name: 'Gửi lại để duyệt' }))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Xác nhận', exact: true }))
  await waitFor(() => expect(api.resubmitPurchase).toHaveBeenCalledWith('access-for-test', 'po1'))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  po.Status = 'Receiving'; po.Items[0].ReceivedQuantity = 1
  await act(() => router.navigate('/admin/purchases'))
  await screen.findByText('PN-API-01')
  await act(() => router.navigate('/admin/purchases/po1?dialog=close'))
  await screen.findByText('Điện thoại - Đen')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Đóng phiếu nhận thiếu' })).not.toBeInTheDocument()
})

test('a view-only direct action URL shows data but no write controls or modal', async () => {
  renderPage('/admin/purchases/po1?dialog=reject', ['admin.portal', 'purchases:view', 'suppliers:view', 'products:view'], 'Staff')
  await screen.findByText('Điện thoại - Đen')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Sửa phiếu|Xác nhận phiếu|Từ chối/ })).not.toBeInTheDocument()
  expect(api.decidePurchase).not.toHaveBeenCalled()
})

test('missing view permission blocks the detail route before purchase, catalog and supplier reads', async () => {
  renderPage('/admin/purchases/po1', ['admin.portal'], 'Staff')
  await screen.findByText('Không có quyền truy cập')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/'))).toBe(false)
})

test('failed detail read is an error, supports retry and retains the back link', async () => {
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/purchase-orders/po1' && failed ? Promise.reject(new Error('Lỗi kết nối.')) : original(...args))
  renderPage()
  await screen.findByText('Lỗi kết nối.')
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '← Danh sách phiếu nhập' })).toBeEnabled()
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Điện thoại - Đen')
})

test('an empty item array keeps the actual table columns without Figma sample rows', async () => {
  po.Items = []
  renderPage()
  await screen.findByText('Phiếu nhập chưa có sản phẩm.')
  expect(screen.getAllByRole('columnheader')).toHaveLength(6)
  expect(screen.queryByText(/iPhone 17|AirPods/)).not.toBeInTheDocument()
})

test('changing the route ID clears the previous order and shows the new read failure', async () => {
  const router = renderPage()
  await screen.findByText('Điện thoại - Đen')
  await act(() => router.navigate('/admin/purchases/missing'))
  await screen.findByText('Không tìm thấy phiếu nhập.')
  expect(screen.queryByText('Điện thoại - Đen')).not.toBeInTheDocument()
  expect(screen.queryByText('Phiếu nhập PN-API-01')).not.toBeInTheDocument()
})
