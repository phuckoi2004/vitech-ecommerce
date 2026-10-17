import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), createBanner: vi.fn(), updateBanner: vi.fn(), deleteBanner: vi.fn(), activateBanner: vi.fn(), deactivateBanner: vi.fn(), uploadProductImage: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/banners.js', async (original) => ({ ...await original(), ...Object.fromEntries(Object.entries(api).filter(([key]) => !['getAdminData', 'uploadProductImage'].includes(key))) }))
vi.mock('../services/product-media.js', () => ({ uploadProductImage: api.uploadProductImage }))
const permissions = ['admin.portal', 'banners:view', 'banners:create', 'banners:update', 'banners:delete']
const banner = { BannerId: 'b1', Title: 'Banner từ API', ImageUrl: 'https://storage.example.test/banner.png', LinkUrl: '/products', DisplayOrder: 1, IsActive: true, StartDate: '2026-10-12T01:30:25.123Z', EndDate: null, CreatedAt: '2026-10-10T01:30:00Z', CreatedByUserId: 'Admin-id' }
let banners
function renderPage(path = '/admin/banners', granted = permissions) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Admin', permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
beforeEach(() => {
  vi.resetAllMocks(); banners = []
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/banners') return structuredClone(banners)
    const found = banners.find((row) => path === '/admin/banners/' + row.BannerId)
    if (found) return structuredClone(found)
    throw new Error('Không tìm thấy banner.')
  })
  api.createBanner.mockImplementation(async (_, body) => { const row = { ...banner, BannerId: 'new', IsActive: true, ...body }; banners.push(row); return row })
  api.updateBanner.mockImplementation(async (_, id, body) => { banners = banners.map((row) => row.BannerId === id ? { ...row, ...body } : row); return banners.find((row) => row.BannerId === id) })
  api.deleteBanner.mockImplementation(async (_, id) => { banners = banners.filter((row) => row.BannerId !== id) })
  api.activateBanner.mockImplementation(async (_, id) => { banners = banners.map((row) => row.BannerId === id ? { ...row, IsActive: true } : row); return banners.find((row) => row.BannerId === id) })
  api.deactivateBanner.mockImplementation(async (_, id) => { banners = banners.map((row) => row.BannerId === id ? { ...row, IsActive: false } : row); return banners.find((row) => row.BannerId === id) })
})

test('empty banner page retains all columns and accurate counts inside the content dropdown', async () => {
  renderPage()
  await screen.findByText('Chưa có banner quảng cáo nào')
  expect(screen.getByText('Hệ thống hiện chưa có banner quảng cáo trong cơ sở dữ liệu.')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 1, name: 'Quản lý banner quảng cáo' })).toBeInTheDocument()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Tiêu đề', 'Hình ảnh', 'Link khi bấm', 'Thứ tự', 'Trạng thái', 'Thao tác'])
  expect(screen.getByText('0 banner')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 banner')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Tin tức & Banner' })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('button', { name: 'Banner', exact: true })).toHaveAttribute('aria-current', 'page')
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Chưa tìm' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  expect(screen.getByRole('searchbox')).toHaveValue('')
})

test('search and status cover the full array, paginate five rows, and reset page on submit', async () => {
  banners = Array.from({ length: 12 }, (_, i) => ({ ...banner, BannerId: 'b' + i, Title: i === 11 ? 'Mục cần tìm' : 'Banner ' + i, IsActive: i !== 11 }))
  const router = renderPage('/admin/banners?page=2')
  await screen.findByText('Hiển thị 6–10 trong 12 banner')
  expect(screen.getByRole('table').querySelectorAll('tbody tr')).toHaveLength(5)
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'MỤC CẦN TÌM' } })
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'inactive' } })
  expect(router.state.location.search).toBe('?page=2')
  fireEvent.click(screen.getByRole('button', { name: 'Tìm kiếm', exact: true }))
  await screen.findByRole('button', { name: 'Xem Mục cần tìm' })
  expect(screen.getByText('Hiển thị 1–1 trong 1 banner')).toBeInTheDocument()
  expect(router.state.location.search).not.toContain('page=')
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  await screen.findByText('12 banner')
})

test('errors retry and unsafe destination links are never made clickable', async () => {
  banners = [{ ...banner, LinkUrl: 'javascript:alert(1)' }]
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((...args) => { if (args[1] === '/admin/banners' && failed) { failed = false; return Promise.reject(new Error('Lỗi tải banner.')) } return original(...args) })
  renderPage()
  await screen.findByText('Lỗi tải banner.')
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText(banner.Title)
  expect(screen.queryByRole('link', { name: 'javascript:alert(1)' })).not.toBeInTheDocument()
  const img = screen.getByRole('img', { name: 'Banner ' + banner.Title })
  expect(img).toHaveAttribute('src', banner.ImageUrl)
  fireEvent.error(img)
  expect(screen.getByText('Không tải được ảnh')).toBeVisible()
})

test('new banners require local upload and block saving/closing until the returned Supabase URL is ready', async () => {
  const router = renderPage('/admin/banners?dialog=new')
  const dialog = await screen.findByRole('region', { name: 'Thêm banner quảng cáo' }), ui = within(dialog)
  expect(router.state.location.pathname).toBe('/admin/banners/new')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Banner', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(ui.queryByRole('textbox', { name: /URL ảnh|Đường dẫn ảnh/i })).not.toBeInTheDocument()
  fireEvent.change(ui.getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: ' Banner mới ' } })
  fireEvent.click(ui.getByRole('button', { name: 'Lưu banner' }))
  await ui.findByText('Vui lòng chọn ảnh banner từ máy và chờ tải lên hoàn tất.')
  expect(api.createBanner).not.toHaveBeenCalled()
  let finish
  api.uploadProductImage.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const file = new File(['test-only-image'], 'banner.png', { type: 'image/png' })
  fireEvent.change(ui.getByLabelText('Tải ảnh banner'), { target: { files: [file] } })
  expect(api.uploadProductImage).toHaveBeenCalledWith('access-for-test', file)
  expect(ui.getByRole('button', { name: 'Hủy' })).toBeDisabled()
  expect(ui.getByRole('button', { name: 'Lưu banner' })).toBeDisabled()
  await act(() => finish({ ImageUrl: 'https://storage.example.test/new.png' }))
  fireEvent.click(ui.getByRole('button', { name: 'Lưu banner' }))
  await waitFor(() => expect(api.createBanner).toHaveBeenCalledWith('access-for-test', { Title: 'Banner mới', ImageUrl: 'https://storage.example.test/new.png', LinkUrl: null, DisplayOrder: 0, StartDate: null, EndDate: null, IsActive: true }))
  await screen.findByText('Đã thêm banner.')
})

test('editing validates links and date ranges, preserves unchanged timestamps, and sends only editable fields', async () => {
  banners = [{ ...banner, IsActive: false }]
  renderPage('/admin/banners?dialog=edit&banner=b1')
  const ui = within(await screen.findByRole('region', { name: 'Sửa banner quảng cáo' }))
  await ui.findByRole('textbox', { name: 'Tiêu đề' })
  expect(ui.getByLabelText('Bắt đầu hiển thị')).toHaveValue('2026-10-12T08:30:25.000')
  fireEvent.change(ui.getByRole('textbox', { name: 'Link khi bấm' }), { target: { value: '//unsafe.test' } })
  fireEvent.click(ui.getByRole('button', { name: 'Cập nhật' }))
  await ui.findByText('Link khi bấm phải là đường dẫn nội bộ bắt đầu bằng / hoặc địa chỉ HTTPS hợp lệ.')
  expect(api.updateBanner).not.toHaveBeenCalled()
  fireEvent.change(ui.getByRole('textbox', { name: 'Link khi bấm' }), { target: { value: '/products?category=phone' } })
  fireEvent.change(ui.getByLabelText('Kết thúc hiển thị'), { target: { value: '2026-10-11T09:00' } })
  fireEvent.click(ui.getByRole('button', { name: 'Cập nhật' }))
  await ui.findByText('Thời điểm kết thúc phải sau hoặc bằng thời điểm bắt đầu.')
  fireEvent.change(ui.getByLabelText('Kết thúc hiển thị'), { target: { value: '2026-10-15T09:00' } })
  fireEvent.click(ui.getByRole('button', { name: 'Cập nhật' }))
  await waitFor(() => expect(api.updateBanner).toHaveBeenCalledWith('access-for-test', 'b1', { Title: banner.Title, ImageUrl: banner.ImageUrl, LinkUrl: '/products?category=phone', DisplayOrder: 1, StartDate: banner.StartDate, EndDate: '2026-10-15T09:00+07:00', IsActive: false }))
  expect(banners[0].IsActive).toBe(false)
})

test('detail toggles status using workflow endpoints and renders actual dates and destination', async () => {
  banners = [{ ...banner, IsActive: false }]
  renderPage('/admin/banners?dialog=view&banner=b1')
  const dialog = within(await screen.findByRole('region', { name: 'Chi tiết banner quảng cáo' }))
  await dialog.findByDisplayValue('12/10/2026 08:30')
  expect(dialog.getByRole('link', { name: '/products' })).toHaveAttribute('href', '/products')
  fireEvent.click(dialog.getByRole('button', { name: 'Bật banner' }))
  await waitFor(() => expect(api.activateBanner).toHaveBeenCalledWith('access-for-test', 'b1'))
  fireEvent.click(await dialog.findByRole('button', { name: 'Ngừng hoạt động' }))
  await waitFor(() => expect(api.deactivateBanner).toHaveBeenCalledWith('access-for-test', 'b1'))
  expect(api.updateBanner).not.toHaveBeenCalled()
})

test('delete cancel has no writes; retry and pending guards work, and last-page deletion clamps pagination', async () => {
  banners = Array.from({ length: 6 }, (_, i) => ({ ...banner, BannerId: 'b' + i, Title: 'Banner ' + i }))
  const router = renderPage('/admin/banners?page=2')
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa Banner 5' }))
  let ui = within(screen.getByRole('dialog'))
  fireEvent.click(await ui.findByRole('button', { name: 'Hủy' }))
  expect(api.deleteBanner).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Xóa Banner 5' }))
  ui = within(screen.getByRole('dialog'))
  api.deleteBanner.mockRejectedValueOnce(new Error('Chưa xóa được banner.'))
  fireEvent.click(await ui.findByRole('button', { name: 'Xác nhận xóa' }))
  await ui.findByText('Chưa xóa được banner.')
  let finish
  api.deleteBanner.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const confirm = ui.getByRole('button', { name: 'Xác nhận xóa' })
  fireEvent.click(confirm); fireEvent.click(confirm)
  expect(api.deleteBanner).toHaveBeenCalledTimes(2)
  expect(ui.getByRole('button', { name: 'Hủy' })).toBeDisabled()
  await act(() => { banners.pop(); finish() })
  await screen.findByText('Hiển thị 1–5 trong 5 banner')
  expect(router.state.location.search).toBe('?page=1')
})

test('view-only permissions cannot open write dialogs, including URL deep links', async () => {
  banners = [banner]
  const router = renderPage('/admin/banners?dialog=delete&banner=b1', ['admin.portal', 'banners:view'])
  await screen.findByText('1 banner')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  for (const mode of ['edit', 'new']) { await act(() => router.navigate('/admin/banners?dialog=' + mode + '&banner=b1')); expect(screen.queryByRole('dialog')).not.toBeInTheDocument() }
  expect(screen.queryByRole('button', { name: '+ Thêm banner' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Xem ' + banner.Title }))
  const ui = within(await screen.findByRole('region', { name: 'Chi tiết banner quảng cáo' }))
  await ui.findByDisplayValue(banner.Title)
  expect(router.state.location.pathname).toBe('/admin/banners/b1')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(ui.queryByRole('button', { name: 'Sửa banner' })).not.toBeInTheDocument()
  expect(ui.queryByRole('button', { name: 'Ngừng hoạt động' })).not.toBeInTheDocument()
  expect(api.deleteBanner).not.toHaveBeenCalled()
})

test('detail and editor have reloadable routes, preserve filters and keep the content menu active', async () => {
  banners = [banner]
  const router = renderPage('/admin/banners/b1?keyword=Banner&status=active')
  const detail = within(await screen.findByRole('region', { name: 'Chi tiết banner quảng cáo' }))
  expect(detail.getByRole('textbox', { name: 'Tiêu đề' })).toHaveAttribute('readonly')
  expect(detail.getByRole('textbox', { name: 'Kết thúc hiển thị' })).toHaveValue('Không giới hạn')
  fireEvent.click(detail.getByRole('button', { name: 'Sửa banner' }))
  const editor = within(await screen.findByRole('region', { name: 'Sửa banner quảng cáo' }))
  expect(router.state.location.pathname).toBe('/admin/banners/b1/edit')
  expect(editor.getAllByRole('option').map((item) => item.textContent)).toEqual(['Hoạt động', 'Ngừng hoạt động'])
  expect(screen.getByRole('button', { name: 'Tin tức & Banner' })).toHaveAttribute('aria-expanded', 'true')
  fireEvent.click(editor.getByRole('button', { name: 'Hủy' }))
  await screen.findByRole('heading', { level: 1, name: 'Quản lý banner quảng cáo' })
  expect(router.state.location.pathname).toBe('/admin/banners')
  expect(router.state.location.search).toBe('?keyword=Banner&status=active')
  expect(api.updateBanner).not.toHaveBeenCalled()
})

test('failed update opens a modal over the same editor and keeps the draft for retry', async () => {
  banners = [banner]
  const router = renderPage('/admin/banners/b1/edit')
  const editor = within(await screen.findByRole('region', { name: 'Sửa banner quảng cáo' }))
  fireEvent.change(editor.getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Tên chưa được lưu' } })
  fireEvent.change(editor.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'inactive' } })
  api.updateBanner.mockRejectedValueOnce(new Error('Máy chủ đang bận.'))
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  const error = await screen.findByRole('dialog', { name: 'Không thể cập nhật banner' })
  expect(within(error).getByText('Hệ thống gặp lỗi khi thay đổi dữ liệu. Dữ liệu cũ được giữ nguyên.')).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/admin/banners/b1/edit')
  expect(banners[0].Title).toBe(banner.Title)
  expect(banners[0].IsActive).toBe(true)
  fireEvent.click(within(error).getByRole('button', { name: 'Đóng thông báo' }))
  expect(editor.getByRole('textbox', { name: 'Tiêu đề' })).toHaveValue('Tên chưa được lưu')
  expect(editor.getByRole('combobox', { name: 'Trạng thái' })).toHaveValue('inactive')
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  await screen.findByText('Đã cập nhật banner.')
  expect(api.updateBanner).toHaveBeenCalledTimes(2)
  expect(api.updateBanner.mock.calls[0]).toEqual(api.updateBanner.mock.calls[1])
  expect(banners[0]).toMatchObject({ Title: 'Tên chưa được lưu', IsActive: false })
  expect(api.deactivateBanner).not.toHaveBeenCalled()
})

test('status-only form edits use one PATCH and leave server metadata untouched', async () => {
  banners = [banner]
  renderPage('/admin/banners/b1/edit')
  const editor = within(await screen.findByRole('region', { name: 'Sửa banner quảng cáo' }))
  fireEvent.change(editor.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'inactive' } })
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  await screen.findByText('Đã cập nhật banner.')
  expect(api.updateBanner).toHaveBeenCalledExactlyOnceWith('access-for-test', 'b1', expect.objectContaining({ IsActive: false }))
  expect(api.updateBanner.mock.calls[0][2]).not.toHaveProperty('CreatedAt')
  expect(api.deactivateBanner).not.toHaveBeenCalled()
  expect(banners[0].CreatedAt).toBe(banner.CreatedAt)
})

test('create sends content and inactive state together; failure saves nothing and retry creates one inactive banner', async () => {
  renderPage('/admin/banners/new')
  const editor = within(await screen.findByRole('region', { name: 'Thêm banner quảng cáo' }))
  fireEvent.change(editor.getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Banner chờ hiển thị' } })
  api.uploadProductImage.mockResolvedValueOnce({ ImageUrl: 'https://storage.example.test/staged.png' })
  fireEvent.change(editor.getByLabelText('Tải ảnh banner'), { target: { files: [new File(['test-image'], 'banner.png', { type: 'image/png' })] } })
  await editor.findByRole('button', { name: 'Thay ảnh từ máy' })
  fireEvent.change(editor.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'inactive' } })
  api.createBanner.mockRejectedValueOnce(new Error('Chưa lưu được banner.'))
  fireEvent.click(editor.getByRole('button', { name: 'Lưu banner' }))
  const error = await screen.findByRole('dialog', { name: 'Không thể lưu banner' })
  expect(within(error).getByText('Chưa lưu được banner.')).toBeInTheDocument()
  expect(banners).toHaveLength(0)
  expect(editor.getByRole('textbox', { name: 'Tiêu đề' })).toHaveValue('Banner chờ hiển thị')
  expect(editor.getByRole('combobox', { name: 'Trạng thái' })).toHaveValue('inactive')
  fireEvent.click(within(error).getByRole('button', { name: 'Đóng thông báo' }))
  fireEvent.click(editor.getByRole('button', { name: 'Lưu banner' }))
  await screen.findByText('Đã thêm banner.')
  expect(api.createBanner).toHaveBeenCalledTimes(2)
  expect(api.createBanner.mock.calls[0]).toEqual(api.createBanner.mock.calls[1])
  expect(api.createBanner).toHaveBeenLastCalledWith('access-for-test', expect.objectContaining({ Title: 'Banner chờ hiển thị', IsActive: false }))
  expect(api.deactivateBanner).not.toHaveBeenCalled()
  expect(banners).toHaveLength(1)
  expect(banners[0].IsActive).toBe(false)
})

test('failed local image replacement retains the saved image; successful replacement sends the new URL', async () => {
  banners = [banner]
  renderPage('/admin/banners/b1/edit')
  const editor = within(await screen.findByRole('region', { name: 'Sửa banner quảng cáo' }))
  const file = new File(['image-for-test'], 'replacement.webp', { type: 'image/webp' })
  api.uploadProductImage.mockRejectedValueOnce(new Error('Không tải được ảnh lên kho lưu trữ.'))
  fireEvent.change(editor.getByLabelText('Tải ảnh banner'), { target: { files: [file] } })
  await editor.findByText('Không tải được ảnh lên kho lưu trữ.')
  expect(editor.getByRole('img', { name: 'Ảnh banner' })).toHaveAttribute('src', banner.ImageUrl)
  expect(api.updateBanner).not.toHaveBeenCalled()
  api.uploadProductImage.mockResolvedValueOnce({ ImageUrl: 'https://storage.example.test/replacement.webp' })
  fireEvent.change(editor.getByLabelText('Tải ảnh banner'), { target: { files: [file] } })
  await waitFor(() => expect(editor.getByRole('img', { name: 'Ảnh banner' })).toHaveAttribute('src', 'https://storage.example.test/replacement.webp'))
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  await waitFor(() => expect(api.updateBanner).toHaveBeenCalledWith('access-for-test', 'b1', expect.objectContaining({ ImageUrl: 'https://storage.example.test/replacement.webp' })))
})

test('pending saves prevent repeated writes and missing records never show an empty edit form', async () => {
  banners = [banner]
  const router = renderPage('/admin/banners/b1/edit')
  const editor = within(await screen.findByRole('region', { name: 'Sửa banner quảng cáo' }))
  fireEvent.change(editor.getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Đang lưu banner' } })
  let finish
  api.updateBanner.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const save = editor.getByRole('button', { name: 'Cập nhật' })
  fireEvent.click(save); fireEvent.click(save)
  expect(api.updateBanner).toHaveBeenCalledTimes(1)
  expect(editor.getByRole('button', { name: 'Hủy' })).toBeDisabled()
  await act(() => finish({ ...banner, Title: 'Đang lưu banner' }))
  await screen.findByText('Đã cập nhật banner.')
  await act(() => router.navigate('/admin/banners/missing/edit'))
  await screen.findByText('Không tìm thấy banner.')
  expect(screen.queryByRole('textbox', { name: 'Tiêu đề' })).not.toBeInTheDocument()
})
