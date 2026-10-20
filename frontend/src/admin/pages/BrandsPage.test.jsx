import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import BrandsPage from './BrandsPage.jsx'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), uploadProductImage: vi.fn(), createBrand: vi.fn(), updateBrand: vi.fn(), deleteBrand: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/brands.js', () => api)
vi.mock('../services/product-media.js', () => ({ uploadProductImage: api.uploadProductImage }))

const brand = { BrandId: 'c1', Name: 'Hãng thiết bị', Slug: 'hang-thiet-bi', Description: 'Mô tả từ API', LogoUrl: null, IsActive: true }
const hidden = { ...brand, BrandId: 'c2', Name: 'Hãng đã ẩn', Slug: 'hang-da-an', IsActive: false }
const permissions = ['admin.portal', 'brands:view', 'brands:create', 'brands:update', 'brands:delete']
let brands

function renderPage(path = '/admin/brands', granted = permissions) {
  const router = createMemoryRouter([{ path: '/admin/brands', element: <BrandsPage /> }], { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Admin', permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

beforeEach(() => {
  vi.clearAllMocks()
  brands = []
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/brands') return [...brands]
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/categories') return []
    if (path === '/admin/variants') return { Items: [], Total: 0 }
    const found = brands.find((item) => path === '/brands/' + item.BrandId)
    if (found) return { ...found }
    throw new Error('Không tìm thấy thương hiệu.')
  })
  api.createBrand.mockImplementation(async (_, body) => {
    const saved = { ...body, BrandId: 'new-brand' }
    brands = [...brands, saved]
    return saved
  })
  api.updateBrand.mockImplementation(async (_, id, body) => {
    brands = brands.map((item) => item.BrandId === id ? { ...item, ...body } : item)
    return brands.find((item) => item.BrandId === id)
  })
  api.deleteBrand.mockImplementation(async (_, id) => { brands = brands.filter((item) => item.BrandId !== id) })
})

test('empty API data retains the four Figma columns and shows zero, without inserting example records', async () => {
  renderPage()
  await screen.findByText('Chưa có thương hiệu.')
  for (const name of ['Tên thương hiệu', 'Mô tả', 'Trạng thái', 'Thao tác']) expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0 thương hiệu')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 thương hiệu')).toBeInTheDocument()
  expect(screen.queryByText('Apple')).not.toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/brands', { active_only: false }, expect.any(AbortSignal))
})

test('real API names, descriptions and visible/hidden badges populate the table', async () => {
  brands = [brand, hidden]
  renderPage()
  await screen.findByText('Hiển thị 2 thương hiệu')
  const rows = within(screen.getByRole('table')).getAllByRole('row')
  expect(rows).toHaveLength(3)
  expect(rows[1]).toHaveTextContent('Hãng thiết bịMô tả từ APIĐang hiển thị')
  expect(rows[2]).toHaveTextContent('Hãng đã ẩnMô tả từ APIĐã ẩn')
  expect(within(rows[1]).getByRole('button', { name: 'Chi tiết Hãng thiết bị' })).toBeInTheDocument()
  expect(screen.queryByText(brand.BrandId)).not.toBeInTheDocument()
})

test('search debounces, combines with status and preserves focus and URL history', async () => {
  brands = [brand, hidden]
  const router = renderPage()
  await screen.findByText('Hiển thị 2 thương hiệu')
  const search = screen.getByRole('searchbox', { name: 'Tìm kiếm thương hiệu theo tên' })
  search.focus()
  fireEvent.change(search, { target: { value: 'HÃNG ĐÃ' } })
  await waitFor(() => expect(router.state.location.search).toBe('?keyword=H%C3%83NG+%C4%90%C3%83'))
  expect(search).toHaveFocus()
  expect(screen.getByText('Hiển thị 1 thương hiệu')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'active' } })
  await screen.findByText('Không có thương hiệu phù hợp.')
  await router.navigate(-1)
  await screen.findByText('Hiển thị 1 thương hiệu')
  expect(screen.getByRole('button', { name: 'Chi tiết Hãng đã ẩn' })).toBeInTheDocument()
})

test('pagination counts the filtered brand array and clamps deep links safely', async () => {
  brands = Array.from({ length: 10 }, (_, i) => ({ ...brand, BrandId: 'page-' + i, Name: 'Thương hiệu ' + i }))
  const router = renderPage('/admin/brands?page=2')
  await screen.findByText('Hiển thị 9–10 trong 10 thương hiệu')
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(3)
  expect(screen.getByRole('button', { name: 'Trang sau' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Trang trước' }))
  await screen.findByText('Hiển thị 1–8 trong 10 thương hiệu')
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(9)
  await router.navigate('/admin/brands?page=99')
  await waitFor(() => expect(router.state.location.search).toBe('?page=2'))
})

test('API errors stay distinct from an empty list and retry recovers', async () => {
  api.getAdminData.mockRejectedValueOnce(new Error('Không kết nối được máy chủ.'))
  renderPage()
  expect(await screen.findByText('Không kết nối được máy chủ.')).toBeInTheDocument()
  expect(screen.queryByText('Hiển thị 0 thương hiệu')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText('Chưa có thương hiệu.')).toBeInTheDocument()
})

test('create suggests a slug, preserves a manually edited slug and sends only supported brand fields', async () => {
  brands = [brand]
  const router = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Thêm thương hiệu' }))
  const dialog = screen.getByRole('dialog', { name: 'Thêm thương hiệu' })
  const user = userEvent.setup()
  await user.type(within(dialog).getByRole('textbox', { name: 'Tên thương hiệu' }), 'Thiết bị mới')
  const slug = within(dialog).getByRole('textbox', { name: 'Đường dẫn (slug)' })
  expect(slug).toHaveValue('thiet-bi-moi')
  fireEvent.change(slug, { target: { value: 'duong-dan-rieng' } })
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Tên thương hiệu' }), { target: { value: 'Thiết bị mới hơn' } })
  expect(slug).toHaveValue('duong-dan-rieng')
  api.uploadProductImage.mockResolvedValueOnce({ ImageUrl: 'https://example.com/brand.png' })
  const file = new File(['logo'], 'brand.png', { type: 'image/png' })
  await user.upload(within(dialog).getByLabelText('Tải ảnh logo thương hiệu'), file)
  expect(api.uploadProductImage).toHaveBeenCalledWith('access-for-test', file)
  expect(within(dialog).queryByRole('textbox', { name: 'Đường dẫn logo' })).not.toBeInTheDocument()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Mô tả' }), { target: { value: 'Mô tả mới' } })
  fireEvent.change(within(dialog).getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'hidden' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm thương hiệu' }))
  await waitFor(() => expect(api.createBrand).toHaveBeenCalledWith('access-for-test', {
    Name: 'Thiết bị mới hơn', Slug: 'duong-dan-rieng', LogoUrl: 'https://example.com/brand.png', Description: 'Mô tả mới', IsActive: false,
  }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(router.state.location.search).toBe('')
  expect(await screen.findByRole('button', { name: 'Chi tiết Thiết bị mới hơn' })).toBeInTheDocument()
})

test('a brand logo can be a pasted link, including http and spaces, but not an embedded data: image', async () => {
  brands = [brand]
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Thêm thương hiệu' }))
  const dialog = screen.getByRole('dialog', { name: 'Thêm thương hiệu' })
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Tên thương hiệu' }), { target: { value: 'Hãng link' } })
  const address = within(dialog).getByRole('textbox', { name: 'Đường dẫn ảnh logo thương hiệu' })
  fireEvent.change(address, { target: { value: 'data:image/png;base64,iVBORw0KGgo=' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Dùng ảnh từ đường dẫn' }))
  expect(within(dialog).getByRole('alert')).toHaveTextContent('ảnh nhúng (data:)')
  fireEvent.change(address, { target: { value: 'http://cdn.example.test/logo hang.png' } })
  fireEvent.keyDown(address, { key: 'Enter' })
  expect(within(dialog).getByRole('img', { name: 'Ảnh logo thương hiệu 1' })).toHaveAttribute('src', 'http://cdn.example.test/logo%20hang.png')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm thương hiệu' }))
  await waitFor(() => expect(api.createBrand).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ Name: 'Hãng link', LogoUrl: 'http://cdn.example.test/logo%20hang.png' })))
  expect(api.uploadProductImage).not.toHaveBeenCalled()
})

test('view reads logo and API details; editing can clear optional values without changing the slug', async () => {
  brands = [{ ...brand, LogoUrl: 'https://example.com/brand.png' }]
  const router = renderPage('/admin/brands?status=active')
  fireEvent.click(await screen.findByRole('button', { name: 'Chi tiết Hãng thiết bị' }))
  let dialog = await screen.findByRole('dialog', { name: 'Chi tiết thương hiệu' })
  expect(await within(dialog).findByText(brand.Slug)).toBeInTheDocument()
  const logo = within(dialog).getByRole('img', { name: 'Logo Hãng thiết bị' })
  expect(logo).toHaveAttribute('src', 'https://example.com/brand.png')
  fireEvent.error(logo)
  expect(within(dialog).getByText('Không tải được logo.')).toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Sửa thương hiệu' }))
  dialog = await screen.findByRole('dialog', { name: 'Sửa thương hiệu' })
  const name = await within(dialog).findByRole('textbox', { name: 'Tên thương hiệu' })
  fireEvent.change(name, { target: { value: 'Tên mới' } })
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Mô tả' }), { target: { value: '' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Bỏ ảnh 1' }))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  await waitFor(() => expect(api.updateBrand).toHaveBeenCalledWith('access-for-test', brand.BrandId, {
    Name: 'Tên mới', Slug: brand.Slug, Description: null, LogoUrl: null, IsActive: true,
  }))
  await waitFor(() => expect(router.state.location.search).toBe('?status=active'))
})

test('failed save retains typed fields and supports correction without losing the form', async () => {
  brands = [brand]
  api.updateBrand.mockRejectedValueOnce(new Error('Slug thương hiệu đã tồn tại'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa Hãng thiết bị' }))
  const dialog = await screen.findByRole('dialog', { name: 'Sửa thương hiệu' })
  const name = await within(dialog).findByRole('textbox', { name: 'Tên thương hiệu' })
  fireEvent.change(name, { target: { value: 'Tên đã sửa' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Slug thương hiệu đã tồn tại')
  expect(name).toHaveValue('Tên đã sửa')
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Đường dẫn (slug)' }), { target: { value: 'ten-da-sua' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  expect(await screen.findByRole('button', { name: 'Chi tiết Tên đã sửa' })).toBeInTheDocument()
})

test('delete requires explicit confirmation, cancel does not write and filters remain intact', async () => {
  brands = [brand, hidden]
  const router = renderPage('/admin/brands?status=hidden')
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa Hãng đã ẩn' }))
  let dialog = await screen.findByRole('dialog', { name: 'Xóa thương hiệu' })
  await within(dialog).findByText(hidden.Name)
  expect(api.deleteBrand).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Hủy' }))
  expect(api.deleteBrand).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Xóa Hãng đã ẩn' }))
  dialog = await screen.findByRole('dialog', { name: 'Xóa thương hiệu' })
  await within(dialog).findByText(hidden.Name)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  await waitFor(() => expect(api.deleteBrand).toHaveBeenCalledWith('access-for-test', hidden.BrandId))
  await screen.findByText('Không có thương hiệu phù hợp.')
  expect(router.state.location.search).toBe('?status=hidden')
})

test('failed soft deletion keeps the dialog and retry does not silently hide the brand', async () => {
  brands = [brand]
  api.deleteBrand.mockRejectedValueOnce(new Error('Không thể lưu thay đổi'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa Hãng thiết bị' }))
  const dialog = await screen.findByRole('dialog', { name: 'Xóa thương hiệu' })
  await within(dialog).findByText(brand.Name)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Không thể lưu thay đổi')
  expect(api.updateBrand).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  await screen.findByText('Đã xóa thương hiệu.')
  expect(api.deleteBrand).toHaveBeenCalledTimes(2)
  expect(api.updateBrand).not.toHaveBeenCalled()
})

test('view-only Staff cannot write or open write forms from direct URLs', async () => {
  brands = [brand]
  const router = renderPage('/admin/brands?dialog=new', ['admin.portal', 'brands:view'])
  await screen.findByText('Hiển thị 1 thương hiệu')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  for (const mode of ['edit', 'delete']) {
    await router.navigate('/admin/brands?dialog=' + mode + '&brand=c1')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: /Thêm thương hiệu|Sửa Hãng|Xóa Hãng/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Chi tiết Hãng thiết bị' }))
  const dialog = await screen.findByRole('dialog', { name: 'Chi tiết thương hiệu' })
  await within(dialog).findByText(brand.Slug)
  expect(within(dialog).queryByRole('button', { name: 'Sửa thương hiệu' })).not.toBeInTheDocument()
  expect(api.createBrand).not.toHaveBeenCalled()
  expect(api.updateBrand).not.toHaveBeenCalled()
  expect(api.deleteBrand).not.toHaveBeenCalled()
})

test('invalid local logo files and blank names are rejected before any API write', async () => {
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Thêm thương hiệu' }))
  const dialog = screen.getByRole('dialog', { name: 'Thêm thương hiệu' })
  const name = within(dialog).getByRole('textbox', { name: 'Tên thương hiệu' })
  const logo = within(dialog).getByLabelText('Tải ảnh logo thương hiệu')
  fireEvent.change(name, { target: { value: ' ' } })
  fireEvent.submit(dialog.querySelector('form'))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Tên thương hiệu không được để trống')
  fireEvent.change(name, { target: { value: 'Hãng mới' } })
  fireEvent.change(logo, { target: { files: [new File(['<svg>'], 'logo.svg', { type: 'image/svg+xml' })] } })
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('JPG, PNG hoặc WEBP')
  expect(within(dialog).queryByRole('img')).not.toBeInTheDocument()
  expect(api.createBrand).not.toHaveBeenCalled()
  expect(api.uploadProductImage).not.toHaveBeenCalled()
})

test('the actual admin route uses the brand page, header and product breadcrumb', async () => {
  brands = [brand]
  const router = createMemoryRouter(adminRoutes, { initialEntries: ['/admin/brands'] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Admin', permissions: [...permissions, 'products:view'] })}><RouterProvider router={router} /></AuthContext.Provider>)
  expect(await screen.findByRole('heading', { level: 1, name: 'Quản lý Thương hiệu' })).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Chi tiết Hãng thiết bị' })).toBeInTheDocument()
  const header = screen.getByRole('banner')
  expect(within(header).getByText('/ Thương hiệu')).toBeInTheDocument()
  fireEvent.click(within(header).getByRole('button', { name: 'Sản phẩm' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/admin/products'))
})
