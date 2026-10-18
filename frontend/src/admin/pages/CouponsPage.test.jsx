import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const reads = vi.hoisted(() => ({ getAdminData: vi.fn() }))
const api = vi.hoisted(() => ({ createCoupon: vi.fn(), updateCoupon: vi.fn(), deleteCoupon: vi.fn() }))
vi.mock('../../services/api/admin.js', () => reads)
vi.mock('../services/coupons.js', async (original) => ({ ...await original(), ...api }))
const program = { PromotionId: 'p1', Name: 'Ưu đãi điện thoại', DiscountType: 'Percentage', DiscountValue: '10.00', MinOrderValue: '2000000', MaxDiscountAmount: '200000', StartDate: '2026-10-01T00:00:00Z', EndDate: '2026-10-31T23:59:59Z', Status: 'Active', Description: 'Mô tả chương trình điện thoại', Products: [], Categories: [] }
const base = { CouponId: 'c1', PromotionId: 'p1', Code: 'PHONE10', Name: 'Mã điện thoại', UsageLimit: 100, UsedCount: 7, IsActive: true, CreatedAt: '2026-10-17T00:00:00Z' }
let rows, programs, readError
beforeEach(() => {
  vi.resetAllMocks(); rows = []; programs = [program, { ...program, PromotionId: 'p2', Name: 'Ưu đãi laptop', DiscountType: 'FixedAmount', DiscountValue: '100000', Status: 'Draft' }]; readError = false
  reads.getAdminData.mockImplementation(async (_, path, query) => {
    if (path.endsWith('/unread-count')) return { Count: 0 }
    if (path === '/admin/promotions') {
      if (readError) throw new Error('Lỗi tải danh sách mã')
      return { Total: programs.length, Items: structuredClone(programs.slice((query.page - 1) * query.page_size, query.page * query.page_size)) }
    }
    const group = programs.find((item) => path === '/admin/promotions/' + item.PromotionId + '/coupons')
    if (group) return structuredClone(rows.filter((item) => item.PromotionId === group.PromotionId))
    const row = rows.find((item) => path === '/admin/coupons/' + item.CouponId)
    if (row) return structuredClone(row)
    const promotion = programs.find((item) => path === '/admin/promotions/' + item.PromotionId)
    if (promotion) return structuredClone(promotion)
    if (path === '/admin/products') return { Total: 0, Items: [] }
    if (path === '/categories') return []
    throw new Error('Không tìm thấy mã giảm giá')
  })
  api.createCoupon.mockImplementation(async (_, body) => { rows.push({ CouponId: 'created', UsedCount: 0, CreatedAt: base.CreatedAt, ...body }) })
  api.updateCoupon.mockImplementation(async (_, id, body) => { rows = rows.map((row) => row.CouponId === id ? { ...row, ...body } : row) })
  api.deleteCoupon.mockImplementation(async (_, id) => { rows = rows.filter((row) => row.CouponId !== id) })
})
function open(path = '/admin/coupons', role = 'Admin', writes = true) {
  const permissions = ['admin.portal', 'promotions:view', ...(writes ? ['promotions:create', 'promotions:update', 'promotions:delete'] : [])]
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
const modal = () => within(screen.getByRole('dialog'))
const table = () => within(screen.getByRole('table'))
const loaded = () => screen.findByText(base.Code, {}, { timeout: 5000 })
async function edit() { rows = [base]; open('/admin/coupons?dialog=edit&coupon=c1'); await screen.findByDisplayValue(base.Code, {}, { timeout: 5000 }); return modal() }

test('empty list keeps columns, zero counts and the selected child of the discount group', async () => {
  open(); await screen.findByText('Chưa có mã giảm giá.', {}, { timeout: 5000 })
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Mã voucher', 'Tên voucher', 'Lượt sử dụng', 'Giá trị', 'Đơn tối thiểu', 'Thời gian', 'Trạng thái', 'Thao tác'])
  expect(screen.getByText('0 voucher')).toBeInTheDocument()
  const nav = within(screen.getByRole('navigation', { name: 'Menu quản trị' }))
  expect(nav.getByRole('button', { name: 'Khuyến mãi', exact: true })).toHaveAttribute('aria-expanded', 'true')
  expect(nav.getByRole('button', { name: 'Mã giảm giá', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(nav.getByRole('button', { name: 'Chương trình khuyến mãi' })).toBeInTheDocument()
})

test('search and filters combine across programs; pagination can advance and filters reset it', async () => {
  rows = Array.from({ length: 8 }, (_, index) => ({ ...base, CouponId: 'c' + index, Code: 'PHONE' + index, PromotionId: index < 7 ? 'p1' : 'p2', IsActive: index !== 7 }))
  const router = open(); await screen.findByText('8 voucher', {}, { timeout: 5000 })
  expect(table().getAllByRole('row')).toHaveLength(7)
  fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
  expect(router.state.location.search).toContain('page=2')
  expect(table().getByText('PHONE6')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: 'Loại giảm giá' }), { target: { value: 'FixedAmount' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Lọc trạng thái mã' }), { target: { value: 'upcoming' } })
  fireEvent.change(screen.getByRole('searchbox', { name: 'Tìm mã giảm giá' }), { target: { value: 'dien thoai' } })
  expect(router.state.location.search).not.toContain('page=')
  expect(table().getByText('PHONE7')).toBeInTheDocument()
  expect(screen.getByText('1 voucher')).toBeInTheDocument()
})

test('create uses a real program and sends coupon fields only, with unlimited usage represented by null', async () => {
  const router = open('/admin/coupons?promotion=p1&dialog=new')
  await screen.findByLabelText('Tên mã giảm giá', {}, { timeout: 5000 })
  const dialog = modal()
  expect(dialog.getByRole('combobox', { name: 'Chương trình khuyến mãi' })).toHaveValue('p1')
  expect(dialog.getByDisplayValue('10%')).toBeInTheDocument()
  expect(dialog.getByDisplayValue('2.000.000đ')).toBeInTheDocument()
  fireEvent.change(dialog.getByLabelText('Mã giảm giá'), { target: { value: ' OCT10 ' } })
  fireEvent.change(dialog.getByLabelText('Tên mã giảm giá'), { target: { value: ' Mã tháng 10 ' } })
  fireEvent.click(dialog.getByRole('button', { name: 'Thêm mã giảm giá', exact: true }))
  await screen.findByText('Đã thêm mã giảm giá.')
  expect(api.createCoupon).toHaveBeenCalledWith('access-for-test', { Code: 'OCT10', Name: 'Mã tháng 10', PromotionId: 'p1', UsageLimit: null })
  expect(router.state.location.search).toBe('?promotion=p1')
  expect(await table().findByText('OCT10')).toBeInTheDocument()
})

test('without any program, adding a code is unavailable and no default code/program is created', async () => {
  programs = []; open('/admin/coupons?dialog=new'); await screen.findByLabelText('Tên mã giảm giá', {}, { timeout: 5000 })
  expect(modal().getByRole('button', { name: 'Thêm mã giảm giá', exact: true })).toBeDisabled()
  expect(modal().getByRole('combobox', { name: 'Chương trình khuyến mãi' }).options).toHaveLength(0)
  expect(modal().getByLabelText('Mô tả chương trình')).toHaveValue('')
  expect(api.createCoupon).not.toHaveBeenCalled()
})

test('detail reads fresh server counts and links to the real program details', async () => {
  rows = [base]; const router = open(); await loaded()
  rows = [{ ...base, UsedCount: 12 }]
  fireEvent.click(screen.getByRole('button', { name: 'Chi tiết mã PHONE10' }))
  await modal().findByText('12/100')
  expect(modal().getByText('Còn 88 lượt')).toBeInTheDocument()
  const link = modal().getByRole('link', { name: /Xem chương trình/ })
  expect(link).toHaveAttribute('href', '/admin/promotions?dialog=view&promotion=p1')
  fireEvent.click(link)
  await screen.findByRole('dialog', { name: 'Chi tiết khuyến mãi' })
  expect(router.state.location.pathname).toBe('/admin/promotions')
})

test('changing program shows inherited terms and saves only the changed coupon field', async () => {
  const dialog = await edit()
  fireEvent.change(dialog.getByRole('combobox', { name: 'Chương trình khuyến mãi' }), { target: { value: 'p2' } })
  expect(dialog.getByDisplayValue('100.000đ')).toBeInTheDocument()
  expect(dialog.getByText('Chưa bắt đầu')).toBeInTheDocument()
  fireEvent.click(dialog.getByRole('button', { name: 'Cập nhật mã' }))
  await screen.findByText('Đã cập nhật mã giảm giá.')
  expect(api.updateCoupon).toHaveBeenCalledWith('access-for-test', 'c1', { PromotionId: 'p2' })
})

test('invalid limits are blocked and editing may clear the old limit without editing UsedCount', async () => {
  const dialog = await edit()
  fireEvent.change(dialog.getByLabelText('Giới hạn lượt dùng'), { target: { value: '6' } })
  fireEvent.submit(dialog.getByRole('button', { name: 'Cập nhật mã' }).closest('form'))
  expect(dialog.getByRole('alert')).toHaveTextContent('không được nhỏ hơn số lượt đã dùng (7)')
  expect(api.updateCoupon).not.toHaveBeenCalled()
  fireEvent.change(dialog.getByLabelText('Giới hạn lượt dùng'), { target: { value: '' } })
  fireEvent.click(dialog.getByRole('button', { name: 'Cập nhật mã' }))
  await screen.findByText('Đã cập nhật mã giảm giá.')
  expect(api.updateCoupon).toHaveBeenCalledWith('access-for-test', 'c1', { UsageLimit: null })
})

test('duplicate code error preserves the form and does not write any program data', async () => {
  api.updateCoupon.mockRejectedValueOnce(Object.assign(new Error('Đã tồn tại'), { code: 'coupon_code_exists' }))
  const dialog = await edit()
  fireEvent.change(dialog.getByLabelText('Mã giảm giá'), { target: { value: 'TAKEN' } })
  fireEvent.click(dialog.getByRole('button', { name: 'Cập nhật mã' }))
  await dialog.findByText(/không phân biệt chữ hoa/)
  expect(dialog.getByLabelText('Mã giảm giá')).toHaveValue('TAKEN')
  expect(rows[0].Code).toBe('PHONE10')
})

test('pending writes block double submits, cancellation and the program link', async () => {
  let finish
  api.updateCoupon.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const dialog = await edit()
  fireEvent.change(dialog.getByLabelText('Tên mã giảm giá'), { target: { value: 'Tên mới' } })
  fireEvent.click(dialog.getByRole('button', { name: 'Cập nhật mã' }))
  fireEvent.click(dialog.getByRole('button', { name: 'Đang lưu…' }))
  fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
  expect(dialog.getByRole('button', { name: 'Hủy', exact: true })).toBeDisabled()
  expect(dialog.getByRole('link', { name: /Xem chương trình/ })).toHaveAttribute('aria-disabled', 'true')
  expect(api.updateCoupon).toHaveBeenCalledTimes(1)
  await act(async () => finish())
  await screen.findByText('Đã cập nhật mã giảm giá.')
})

test('deletion requires confirmation, deletes the coupon only and refreshes the list', async () => {
  rows = [base]; open(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Xóa mã PHONE10' }))
  await screen.findByRole('dialog', { name: 'Xóa mã giảm giá?' })
  expect(api.deleteCoupon).not.toHaveBeenCalled()
  fireEvent.click(await modal().findByRole('button', { name: 'Xóa mã giảm giá', exact: true }))
  await screen.findByText('Đã xóa mã giảm giá.')
  expect(api.deleteCoupon).toHaveBeenCalledWith('access-for-test', 'c1')
  expect(programs).toHaveLength(2)
  expect(await screen.findByText('Chưa có mã giảm giá.')).toBeInTheDocument()
})

test('a used coupon cannot be deleted and no manual pause action is offered', async () => {
  rows = [base]; api.deleteCoupon.mockRejectedValueOnce(Object.assign(new Error('Đã dùng'), { code: 'coupon_in_use' }))
  open('/admin/coupons?dialog=delete&coupon=c1')
  fireEvent.click(await modal().findByRole('button', { name: 'Xóa mã giảm giá', exact: true }))
  await modal().findByText('Mã đã được đơn hàng sử dụng nên không thể xóa.')
  expect(modal().queryByRole('button', { name: /Tạm ngừng/ })).not.toBeInTheDocument()
  expect(api.updateCoupon).not.toHaveBeenCalled()
  expect(rows).toHaveLength(1)
})

test('state is server-owned and a failed edit retains the entire form for retry', async () => {
  api.updateCoupon.mockRejectedValueOnce(new Error('Lỗi lưu mã'))
  const dialog = await edit()
  expect(dialog.queryByRole('combobox', { name: 'Điều chỉnh trạng thái' })).not.toBeInTheDocument()
  expect(dialog.getByLabelText('Trạng thái')).toHaveAttribute('readonly')
  fireEvent.change(dialog.getByLabelText('Tên mã giảm giá'), { target: { value: 'Tên mới' } })
  fireEvent.click(dialog.getByRole('button', { name: 'Cập nhật mã' }))
  await dialog.findByText('Lỗi lưu mã')
  expect(rows[0].Name).toBe(base.Name)
  fireEvent.click(dialog.getByRole('button', { name: 'Cập nhật mã' }))
  await screen.findByText('Đã cập nhật mã giảm giá.')
  expect(api.updateCoupon).toHaveBeenLastCalledWith('access-for-test', 'c1', { Name: 'Tên mới' })
})

test('usage counters come from each coupon while discount, minimum and dates come from its parent program', async () => {
  programs = [{ ...program, Status: 'Draft', MinOrderValue: '3500000', DiscountValue: '15' }]
  rows = [{ ...base, UsedCount: 0, UsageLimit: 50 }, { ...base, CouponId: 'c2', Code: 'SECOND', UsedCount: 9, UsageLimit: 20, IsActive: false }]
  open(); await loaded()
  expect(table().getByText('0/50')).toBeInTheDocument()
  expect(table().getByText('9/20')).toBeInTheDocument()
  expect(table().getAllByText('15%')).toHaveLength(2)
  expect(table().getAllByText('3.500.000đ')).toHaveLength(2)
  expect(table().getAllByText('Chưa bắt đầu')).toHaveLength(2)
  expect(table().getAllByRole('button')).toHaveLength(6)
  expect(table().queryByRole('columnheader', { name: 'Loại giảm' })).not.toBeInTheDocument()
})

test('validity filter uses parent dates independently of the coupon enabled flag, and reset clears every filter', async () => {
  programs = [{ ...program, StartDate: '2000-01-01T00:00:00Z', EndDate: '2100-12-31T23:59:59Z' }, { ...program, PromotionId: 'p2', StartDate: '2200-01-01T00:00:00Z', EndDate: '2200-12-31T23:59:59Z' }]
  rows = [base, { ...base, CouponId: 'future', Code: 'FUTURE', PromotionId: 'p2', IsActive: false }]
  const router = open(); await loaded()
  fireEvent.change(screen.getByRole('combobox', { name: 'Hiệu lực chương trình' }), { target: { value: 'upcoming' } })
  expect(table().getByText('FUTURE')).toBeInTheDocument()
  expect(table().queryByText(base.Code)).not.toBeInTheDocument()
  expect(table().getByText('Chưa bắt đầu')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: 'Lọc trạng thái mã' }), { target: { value: 'active' } })
  expect(screen.getByText('Không có mã giảm giá phù hợp.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Đặt lại' }))
  expect(table().getByText(base.Code)).toBeInTheDocument()
  expect(router.state.location.search).toBe('')
})

test('failed list reads show retry without a false empty count', async () => {
  readError = true; open(); await screen.findByText('Lỗi tải danh sách mã', {}, { timeout: 5000 })
  expect(screen.queryByText('0 voucher')).not.toBeInTheDocument()
  readError = false; fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Chưa có mã giảm giá.')
})

test('backend Admin-only access is respected and Staff query parameters cannot trigger reads or writes', async () => {
  open('/admin/coupons?dialog=new', 'Staff'); await screen.findByRole('alert', {}, { timeout: 5000 })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(reads.getAdminData.mock.calls.some(([, path]) => path.includes('/promotions') || path.includes('/coupons'))).toBe(false)
  expect(api.createCoupon).not.toHaveBeenCalled()
})

test('view-only permissions hide write controls and reject write query parameters', async () => {
  rows = [base]; open('/admin/coupons?dialog=edit&coupon=c1', 'Admin', false); await loaded()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '+ Thêm mã giảm giá' })).not.toBeInTheDocument()
  expect(table().getAllByRole('button')).toHaveLength(1)
})

test('canceling edit preserves filters without changing data', async () => {
  rows = [base]; const router = open('/admin/coupons?promotion=p1&status=active&dialog=edit&coupon=c1')
  await screen.findByDisplayValue(base.Code, {}, { timeout: 5000 })
  fireEvent.click(modal().getByRole('button', { name: 'Hủy', exact: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(router.state.location.search).toContain('promotion=p1')
  expect(router.state.location.search).toContain('status=active')
  expect(api.updateCoupon).not.toHaveBeenCalled()
})
test('form readiness requires name, code and a real program; all inherited fields and usage count are read-only', async () => {
  open('/admin/coupons?dialog=new'); await screen.findByLabelText('Tên mã giảm giá', {}, { timeout: 5000 })
  const dialog = modal(), save = dialog.getByRole('button', { name: 'Thêm mã giảm giá', exact: true })
  expect(save).toBeDisabled()
  fireEvent.change(dialog.getByLabelText('Tên mã giảm giá'), { target: { value: 'Tên voucher riêng' } })
  fireEvent.change(dialog.getByLabelText('Mã giảm giá'), { target: { value: 'SEPARATECODE' } })
  expect(save).toBeDisabled()
  fireEvent.change(dialog.getByRole('combobox', { name: 'Chương trình khuyến mãi' }), { target: { value: 'p1' } })
  expect(save).toBeEnabled()
  expect(dialog.getByLabelText('Mô tả chương trình')).toHaveValue(program.Description)
  for (const label of ['Mô tả chương trình', 'Loại giảm giá', 'Giá trị giảm', 'Đơn hàng tối thiểu', 'Thời gian bắt đầu', 'Thời gian kết thúc', 'Giảm tối đa', 'Lượt đã sử dụng']) {
    expect(dialog.getByLabelText(label)).toHaveAttribute('readonly')
    expect(dialog.getByLabelText(label).className).toContain('bg-admin-page')
  }
  fireEvent.change(dialog.getByRole('combobox', { name: 'Chương trình khuyến mãi' }), { target: { value: 'p2' } })
  expect(dialog.getByLabelText('Giá trị giảm')).toHaveValue('100.000đ')
  expect(dialog.getByLabelText('Tên mã giảm giá')).toHaveValue('Tên voucher riêng')
  expect(dialog.getByLabelText('Mã giảm giá')).toHaveValue('SEPARATECODE')
  fireEvent.click(save)
  await screen.findByText('Đã thêm mã giảm giá.')
  expect(api.createCoupon).toHaveBeenCalledWith('access-for-test', { Name: 'Tên voucher riêng', Code: 'SEPARATECODE', PromotionId: 'p2', UsageLimit: null })
})

test('four server statuses are used without offering manual pause controls', async () => {
  programs = [{ ...program, StartDate: '2000-01-01T00:00:00Z', EndDate: '2100-01-01T00:00:00Z' }, { ...program, PromotionId: 'p2', EndDate: '2000-01-01T00:00:00Z', Status: 'Expired' }]
  rows = [{ ...base, UsedCount: 100 }, { ...base, CouponId: 'upcoming', Code: 'UPCOMING', Status: 'Upcoming', IsActive: false }, { ...base, CouponId: 'expired', Code: 'EXPIRED', PromotionId: 'p2', IsActive: false }]
  open(); await loaded()
  expect(table().getByText('Hết lượt')).toBeInTheDocument()
  expect(table().getByText('Chưa bắt đầu')).toBeInTheDocument()
  expect(table().getByText('Hết chương trình')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: 'Lọc trạng thái mã' }), { target: { value: 'expired' } })
  expect(table().getByText('EXPIRED')).toBeInTheDocument()
  expect(table().queryByText('UPCOMING')).not.toBeInTheDocument()
  expect(api.updateCoupon).not.toHaveBeenCalled()
})

test('pending deletion prevents duplicate requests and blocks dismissing the confirmation', async () => {
  rows = [base]; let finish
  api.deleteCoupon.mockImplementationOnce(() => new Promise((resolve) => { finish = () => { rows = []; resolve() } }))
  open('/admin/coupons?dialog=delete&coupon=c1')
  fireEvent.click(await modal().findByRole('button', { name: 'Xóa mã giảm giá', exact: true }))
  fireEvent.click(modal().getByRole('button', { name: 'Đang xóa…' }))
  fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
  expect(modal().getByRole('button', { name: 'Hủy', exact: true })).toBeDisabled()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(api.deleteCoupon).toHaveBeenCalledTimes(1)
  await act(async () => finish())
  await screen.findByText('Đã xóa mã giảm giá.')
})

test('canceling delete preserves list filters and leaves the coupon intact', async () => {
  rows = [base]; const router = open('/admin/coupons?keyword=PHONE10&dialog=delete&coupon=c1')
  await modal().findByRole('button', { name: 'Xóa mã giảm giá', exact: true })
  fireEvent.click(modal().getByRole('button', { name: 'Hủy', exact: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(router.state.location.search).toBe('?keyword=PHONE10')
  expect(rows).toHaveLength(1)
  expect(api.deleteCoupon).not.toHaveBeenCalled()
})

test.each(['edit', 'delete'])('detail action opens the %s popup with the same coupon and preserves filters', async (mode) => {
  rows = [base]; const router = open('/admin/coupons?keyword=PHONE10&dialog=view&coupon=c1')
  fireEvent.click(await modal().findByRole('button', { name: mode === 'edit' ? 'Sửa thông tin' : 'Xóa mã', exact: true }))
  if (mode === 'edit') await modal().findByDisplayValue(base.Code)
  else await modal().findByRole('button', { name: 'Xóa mã giảm giá', exact: true })
  expect(router.state.location.pathname).toBe('/admin/coupons')
  expect(router.state.location.search).toContain('keyword=PHONE10')
  expect(router.state.location.search).toContain('dialog=' + mode)
  expect(router.state.location.search).toContain('coupon=c1')
  expect(api.deleteCoupon).not.toHaveBeenCalled()
  expect(api.updateCoupon).not.toHaveBeenCalled()
})

test('coupon details show the server creator name and creation timestamp', async () => {
  rows = [{ ...base, CreatedByUserId: 'another-admin', CreatedByName: 'Người tạo mã', CreatedAt: '2026-10-11T02:00:00Z' }]
  open('/admin/coupons?dialog=view&coupon=c1')
  expect(await modal().findByText('Người tạo mã')).toBeInTheDocument()
  expect(modal().getByText(/11\/10\/2026/)).toBeInTheDocument()
})

test('new form previews the parent server time rather than the computer calendar', async () => {
  programs = [{ ...program, Status: 'Scheduled', StartDate: '2000-01-01T00:00:00Z', EndDate: '2000-12-31T00:00:00Z', EvaluatedAt: '1999-12-31T00:00:00Z' }]
  open('/admin/coupons?promotion=p1&dialog=new')
  await screen.findByLabelText('Tên mã giảm giá', {}, { timeout: 5000 })
  expect(modal().getByText('Chưa bắt đầu')).toBeInTheDocument()
  expect(modal().queryByText('Hết chương trình')).not.toBeInTheDocument()
})

