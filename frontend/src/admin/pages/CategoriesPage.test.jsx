import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import CategoriesPage from './CategoriesPage.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), uploadProductImage: vi.fn(), createCategory: vi.fn(), updateCategory: vi.fn(), deleteCategory: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/categories.js', () => api)
vi.mock('../services/product-media.js', () => ({ uploadProductImage: api.uploadProductImage }))

const category = { CategoryId: 'c1', Name: 'Nhóm thiết bị', Slug: 'nhom-thiet-bi', Description: 'Mô tả từ API', ParentCategoryId: null, DisplayOrder: 0, IsActive: true }
const hidden = { ...category, CategoryId: 'c2', Name: 'Nhóm đã ẩn', Slug: 'nhom-da-an', IsActive: false }
const permissions = ['admin.portal', 'categories:view', 'categories:create', 'categories:update', 'categories:delete']
let categories

function renderPage(path = '/admin/categories', granted = permissions) {
  const router = createMemoryRouter([{ path: '/admin/categories', element: <CategoriesPage /> }], { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Admin', permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

beforeEach(() => {
  vi.clearAllMocks()
  categories = []
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/categories') return [...categories]
    const found = categories.find((item) => path === '/categories/' + item.CategoryId)
    if (found) return { ...found }
    throw new Error('Không tìm thấy danh mục.')
  })
  api.createCategory.mockImplementation(async (_, body) => {
    const saved = { ...body, CategoryId: 'new-category' }
    categories = [...categories, saved]
    return saved
  })
  api.updateCategory.mockImplementation(async (_, id, body) => {
    categories = categories.map((item) => item.CategoryId === id ? { ...item, ...body } : item)
    return categories.find((item) => item.CategoryId === id)
  })
  api.deleteCategory.mockImplementation(async (_, id) => { categories = categories.filter((item) => item.CategoryId !== id) })
})

test('empty API data retains the four Figma columns and shows zero, without inserting example records', async () => {
  renderPage()
  await screen.findByText('Chưa có danh mục.')
  for (const name of ['Tên danh mục', 'Mô tả', 'Trạng thái', 'Thao tác']) expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0 danh mục')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 danh mục')).toBeInTheDocument()
  expect(screen.queryByText('Điện thoại')).not.toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/categories', { active_only: false }, expect.any(AbortSignal))
})

test('real API names, descriptions and visible/hidden badges populate the table', async () => {
  categories = [category, hidden]
  renderPage()
  await screen.findByText('Hiển thị 2 danh mục')
  const rows = within(screen.getByRole('table')).getAllByRole('row')
  expect(rows).toHaveLength(3)
  expect(rows[1]).toHaveTextContent('Nhóm thiết bịMô tả từ APIĐang hiển thị')
  expect(rows[2]).toHaveTextContent('Nhóm đã ẩnMô tả từ APIĐã ẩn')
  expect(within(rows[1]).getByRole('button', { name: 'Chi tiết Nhóm thiết bị' })).toBeInTheDocument()
  expect(screen.queryByText(category.CategoryId)).not.toBeInTheDocument()
})

test('search debounces, combines with status and preserves focus and URL history', async () => {
  categories = [category, hidden]
  const router = renderPage()
  await screen.findByText('Hiển thị 2 danh mục')
  const search = screen.getByRole('searchbox', { name: 'Tìm kiếm danh mục theo tên' })
  search.focus()
  fireEvent.change(search, { target: { value: 'NHÓM ĐÃ' } })
  await waitFor(() => expect(router.state.location.search).toBe('?keyword=NH%C3%93M+%C4%90%C3%83'))
  expect(search).toHaveFocus()
  expect(await screen.findByText('Hiển thị 1 danh mục')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'active' } })
  await screen.findByText('Không có danh mục phù hợp.')
  await router.navigate(-1)
  await screen.findByText('Hiển thị 1 danh mục')
  expect(screen.getByRole('button', { name: 'Chi tiết Nhóm đã ẩn' })).toBeInTheDocument()
})

test('pagination counts the filtered category array and clamps deep links safely', async () => {
  categories = Array.from({ length: 10 }, (_, i) => ({ ...category, CategoryId: 'page-' + i, Name: 'Danh mục ' + i }))
  const router = renderPage('/admin/categories?page=2')
  await screen.findByText('Hiển thị 9–10 trong 10 danh mục')
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(3)
  expect(screen.getByRole('button', { name: 'Trang sau' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Trang trước' }))
  await screen.findByText('Hiển thị 1–8 trong 10 danh mục')
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(9)
  await router.navigate('/admin/categories?page=99')
  await waitFor(() => expect(router.state.location.search).toBe('?page=2'))
})

test('API errors stay distinct from an empty list and retry recovers', async () => {
  api.getAdminData.mockRejectedValueOnce(new Error('Không kết nối được máy chủ.'))
  renderPage()
  expect(await screen.findByText('Không kết nối được máy chủ.')).toBeInTheDocument()
  expect(screen.queryByText('Hiển thị 0 danh mục')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText('Chưa có danh mục.')).toBeInTheDocument()
})

test('create suggests a slug, preserves a manually edited slug and sends only supported category fields', async () => {
  categories = [category]
  const router = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Thêm danh mục' }))
  const dialog = screen.getByRole('dialog', { name: 'Thêm danh mục' })
  const user = userEvent.setup()
  await user.type(within(dialog).getByRole('textbox', { name: 'Tên danh mục' }), 'Thiết bị mới')
  const slug = within(dialog).getByRole('textbox', { name: 'Đường dẫn (slug)' })
  expect(slug).toHaveValue('thiet-bi-moi')
  fireEvent.change(slug, { target: { value: 'duong-dan-rieng' } })
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Tên danh mục' }), { target: { value: 'Thiết bị mới hơn' } })
  expect(slug).toHaveValue('duong-dan-rieng')
  fireEvent.change(within(dialog).getByRole('combobox', { name: 'Danh mục cha' }), { target: { value: category.CategoryId } })
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Mô tả' }), { target: { value: 'Mô tả mới' } })
  fireEvent.change(within(dialog).getByRole('spinbutton', { name: 'Thứ tự hiển thị' }), { target: { value: '2' } })
  fireEvent.change(within(dialog).getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'hidden' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm danh mục' }))
  await waitFor(() => expect(api.createCategory).toHaveBeenCalledWith('access-for-test', {
    Name: 'Thiết bị mới hơn', Slug: 'duong-dan-rieng', ParentCategoryId: category.CategoryId, Description: 'Mô tả mới', ImageUrl: null, DisplayOrder: 2, IsActive: false,
  }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(router.state.location.search).toBe('')
  expect(await screen.findByRole('button', { name: 'Chi tiết Thiết bị mới hơn' })).toBeInTheDocument()
})

test('optional category images can be pasted and removed when editing', async () => {
  categories = [category]
  renderPage('/admin/categories?dialog=edit&category=c1')
  let dialog = await screen.findByRole('dialog', { name: 'Sửa danh mục' })
  const address = await within(dialog).findByRole('textbox', { name: 'Đường dẫn ảnh danh mục' })
  fireEvent.change(address, { target: { value: 'https://cdn.example.test/category phone.png' } })
  fireEvent.keyDown(address, { key: 'Enter' })
  expect(within(dialog).getByRole('img', { name: 'Ảnh danh mục 1' })).toHaveAttribute('src', 'https://cdn.example.test/category%20phone.png')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  await waitFor(() => expect(api.updateCategory).toHaveBeenCalledWith('access-for-test', category.CategoryId, expect.objectContaining({ ImageUrl: 'https://cdn.example.test/category%20phone.png' })))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Chi tiết Nhóm thiết bị' }))
  dialog = await screen.findByRole('dialog', { name: 'Chi tiết danh mục' })
  expect(await within(dialog).findByRole('img', { name: 'Ảnh danh mục 1' })).toHaveAttribute('src', 'https://cdn.example.test/category%20phone.png')
  expect(within(dialog).queryByRole('button', { name: 'Bỏ ảnh 1' })).not.toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Sửa danh mục' }))
  dialog = await screen.findByRole('dialog', { name: 'Sửa danh mục' })
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Bỏ ảnh 1' }))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  await waitFor(() => expect(api.updateCategory).toHaveBeenLastCalledWith('access-for-test', category.CategoryId, expect.objectContaining({ ImageUrl: null })))
})

test('upload uses the existing image service and blocks saving until the image is ready', async () => {
  let finish
  api.uploadProductImage.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  renderPage('/admin/categories?dialog=new')
  const dialog = await screen.findByRole('dialog', { name: 'Thêm danh mục' })
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Tên danh mục' }), { target: { value: 'Nhóm có ảnh' } })
  const file = new File(['image'], 'category.png', { type: 'image/png' })
  fireEvent.change(within(dialog).getByLabelText('Tải ảnh danh mục'), { target: { files: [file] } })
  await waitFor(() => expect(api.uploadProductImage).toHaveBeenCalledWith('access-for-test', file))
  expect(within(dialog).getByRole('button', { name: 'Thêm danh mục' })).toBeDisabled()
  expect(api.createCategory).not.toHaveBeenCalled()
  finish({ ImageUrl: 'https://cdn.example.test/uploaded.png' })
  await within(dialog).findByRole('img', { name: 'Ảnh danh mục 1' })
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Thêm danh mục' })).toBeEnabled())
  fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm danh mục' }))
  await waitFor(() => expect(api.createCategory).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ ImageUrl: 'https://cdn.example.test/uploaded.png' })))
})

test('view shows API details and edit excludes itself and descendants as parent choices', async () => {
  const child = { ...hidden, ParentCategoryId: category.CategoryId, Name: 'Danh mục con' }
  const grandchild = { ...category, CategoryId: 'c3', ParentCategoryId: child.CategoryId, Name: 'Danh mục cháu' }
  const other = { ...category, CategoryId: 'c4', Name: 'Nhóm khác' }
  categories = [category, child, grandchild, other]
  const router = renderPage('/admin/categories?status=active')
  fireEvent.click(await screen.findByRole('button', { name: 'Chi tiết Nhóm thiết bị' }))
  let dialog = await screen.findByRole('dialog', { name: 'Chi tiết danh mục' })
  expect(await within(dialog).findByText(category.Slug)).toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Sửa danh mục' }))
  dialog = await screen.findByRole('dialog', { name: 'Sửa danh mục' })
  const parent = await within(dialog).findByRole('combobox', { name: 'Danh mục cha' })
  expect(within(parent).queryByRole('option', { name: category.Name })).not.toBeInTheDocument()
  expect(within(parent).queryByRole('option', { name: /Danh mục con|Danh mục cháu/ })).not.toBeInTheDocument()
  expect(within(parent).getByRole('option', { name: other.Name })).toBeInTheDocument()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Mô tả' }), { target: { value: '' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  await waitFor(() => expect(api.updateCategory).toHaveBeenCalledWith('access-for-test', category.CategoryId, expect.objectContaining({ Description: null })))
  await waitFor(() => expect(router.state.location.search).toBe('?status=active'))
})

test('failed save retains typed fields and supports correction without losing the form', async () => {
  categories = [category]
  api.updateCategory.mockRejectedValueOnce(new Error('Slug danh mục đã tồn tại'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa Nhóm thiết bị' }))
  const dialog = await screen.findByRole('dialog', { name: 'Sửa danh mục' })
  const name = await within(dialog).findByRole('textbox', { name: 'Tên danh mục' })
  fireEvent.change(name, { target: { value: 'Tên đã sửa' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Slug danh mục đã tồn tại')
  expect(name).toHaveValue('Tên đã sửa')
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Đường dẫn (slug)' }), { target: { value: 'ten-da-sua' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
  expect(await screen.findByRole('button', { name: 'Chi tiết Tên đã sửa' })).toBeInTheDocument()
})

test('delete requires explicit confirmation, cancel does not write and filters remain intact', async () => {
  categories = [category, hidden]
  const router = renderPage('/admin/categories?status=hidden')
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa Nhóm đã ẩn' }))
  let dialog = await screen.findByRole('dialog', { name: 'Xóa danh mục' })
  await within(dialog).findByText(hidden.Name)
  expect(api.deleteCategory).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Hủy' }))
  expect(api.deleteCategory).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Xóa Nhóm đã ẩn' }))
  dialog = await screen.findByRole('dialog', { name: 'Xóa danh mục' })
  await within(dialog).findByText(hidden.Name)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  await waitFor(() => expect(api.deleteCategory).toHaveBeenCalledWith('access-for-test', hidden.CategoryId))
  await screen.findByText('Không có danh mục phù hợp.')
  expect(router.state.location.search).toBe('?status=hidden')
})

test('failed soft deletion keeps the dialog and retry does not silently hide the category', async () => {
  categories = [category]
  api.deleteCategory.mockRejectedValueOnce(new Error('Không thể lưu thay đổi'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa Nhóm thiết bị' }))
  const dialog = await screen.findByRole('dialog', { name: 'Xóa danh mục' })
  await within(dialog).findByText(category.Name)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Không thể lưu thay đổi')
  expect(api.updateCategory).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  await screen.findByText('Đã xóa danh mục.')
  expect(api.deleteCategory).toHaveBeenCalledTimes(2)
  expect(api.updateCategory).not.toHaveBeenCalled()
})

test('view-only Staff cannot write or open write forms from direct URLs', async () => {
  categories = [category]
  const router = renderPage('/admin/categories?dialog=new', ['admin.portal', 'categories:view'])
  await screen.findByText('Hiển thị 1 danh mục')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  for (const mode of ['edit', 'delete']) {
    await router.navigate('/admin/categories?dialog=' + mode + '&category=c1')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: /Thêm danh mục|Sửa Nhóm|Xóa Nhóm/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Chi tiết Nhóm thiết bị' }))
  const dialog = await screen.findByRole('dialog', { name: 'Chi tiết danh mục' })
  await within(dialog).findByText(category.Slug)
  expect(within(dialog).queryByRole('button', { name: 'Sửa danh mục' })).not.toBeInTheDocument()
  expect(api.createCategory).not.toHaveBeenCalled()
  expect(api.updateCategory).not.toHaveBeenCalled()
  expect(api.deleteCategory).not.toHaveBeenCalled()
})
