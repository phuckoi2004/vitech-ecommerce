import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), createNews: vi.fn(), updateNews: vi.fn(), deleteNews: vi.fn(), publishNews: vi.fn(), hideNews: vi.fn(), uploadProductImage: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/news.js', async (original) => ({ ...await original(), ...Object.fromEntries(Object.entries(api).filter(([key]) => !['getAdminData', 'uploadProductImage'].includes(key))) }))
vi.mock('../services/product-media.js', () => ({ uploadProductImage: api.uploadProductImage }))
const permissions = ['admin.portal', 'news:view', 'news:create', 'news:update', 'news:delete', 'banners:view', 'users:read']
const article = { NewsArticleId: 'a1', Title: 'Tin tức từ API', Slug: 'tin-tu-api', Summary: 'Tóm tắt thật', Content: 'Nội dung thật', ThumbnailUrl: null, Status: 'Published', PublishedAt: '2026-10-12T01:30:00Z', CreatedAt: '2026-10-10T01:30:00Z', CreatedByUserId: 'other-admin' }
let articles
function renderPage(path = '/admin/news', granted = permissions) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Admin', permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
beforeEach(() => {
  vi.resetAllMocks(); articles = []
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/news') return { Items: structuredClone(articles.slice((query.page - 1) * query.page_size, query.page * query.page_size)), Total: articles.length }
    if (path === '/admin/users/other-admin') return { UserId: 'other-admin', FullName: 'Tên tác giả thật' }
    if (path === '/admin/banners') return []
    const found = articles.find((row) => path === '/admin/news/' + row.NewsArticleId)
    if (found) return structuredClone(found)
    throw new Error('Không tìm thấy bài viết.')
  })
  api.deleteNews.mockImplementation(async (_, id) => { articles = articles.filter((row) => row.NewsArticleId !== id) })
  api.createNews.mockImplementation(async (_, body) => { const row = { ...article, ...body, NewsArticleId: 'new', Status: 'Draft', PublishedAt: null }; articles.push(row); return row })
  api.updateNews.mockImplementation(async (_, id, body) => { articles = articles.map((row) => row.NewsArticleId === id ? { ...row, ...body } : row); return articles.find((row) => row.NewsArticleId === id) })
  api.publishNews.mockImplementation(async (_, id) => { articles = articles.map((row) => row.NewsArticleId === id ? { ...row, Status: 'Published' } : row); return articles.find((row) => row.NewsArticleId === id) })
  api.hideNews.mockImplementation(async (_, id) => { articles = articles.map((row) => row.NewsArticleId === id ? { ...row, Status: 'Hidden' } : row); return articles.find((row) => row.NewsArticleId === id) })
})

test('empty news retains six columns, accurate zero counts and the new dropdown routes', async () => {
  const router = renderPage()
  await screen.findByText('Chưa có tin tức nào')
  expect(screen.getByText('Hệ thống hiện chưa có tin tức trong cơ sở dữ liệu.')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 1, name: 'Quản lý tin tức' })).toBeInTheDocument()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Tiêu đề', 'Tóm tắt', 'Người tạo', 'Trạng thái', 'Thời điểm đăng', 'Thao tác'])
  expect(screen.getByText('0 bài viết')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 bài viết')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Chưa tìm kiếm' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  expect(screen.getByRole('searchbox')).toHaveValue('')
  const menu = within(screen.getByRole('navigation', { name: 'Menu quản trị' }))
  const parent = menu.getByRole('button', { name: 'Tin tức & Banner' })
  expect(parent).toHaveAttribute('aria-expanded', 'true')
  fireEvent.click(parent); expect(parent).toHaveAttribute('aria-expanded', 'false')
  fireEvent.click(parent)
  fireEvent.click(menu.getByRole('button', { name: 'Banner', exact: true }))
  await screen.findByRole('heading', { level: 1, name: 'Quản lý banner quảng cáo' })
  expect(router.state.location.pathname).toBe('/admin/banners')
})

test('search covers every API page, then combines status and resets pagination only on submit', async () => {
  articles = Array.from({ length: 101 }, (_, i) => ({ ...article, NewsArticleId: 'a' + i, Title: 'Bài ' + i, Slug: 'bai-' + i, Status: i === 100 ? 'Draft' : 'Published' }))
  const router = renderPage('/admin/news?page=2')
  await screen.findByText('101 bài viết')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/news', { page: 2, page_size: 100 }, expect.any(AbortSignal))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'bai-100' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Trạng thái tin tức' }), { target: { value: 'Draft' } })
  expect(router.state.location.search).toBe('?page=2')
  fireEvent.click(screen.getByRole('button', { name: 'Tìm kiếm', exact: true }))
  await screen.findByText('1 bài viết')
  expect(screen.getByRole('button', { name: 'Xem Bài 100' })).toBeInTheDocument()
  expect(router.state.location.search).toContain('keyword=bai-100')
  expect(router.state.location.search).not.toContain('page=')
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  await screen.findByText('101 bài viết')
  expect(screen.getByRole('searchbox')).toHaveValue('')
})

test('API author names, states and published timestamps display without fake example data', async () => {
  articles = [article, { ...article, NewsArticleId: 'draft', Title: 'Bài nháp', Status: 'Draft', PublishedAt: null }]
  renderPage()
  await screen.findAllByText('Tên tác giả thật')
  expect(screen.getByText('12/10/2026 08:30')).toBeInTheDocument()
  expect(within(screen.getByRole('table')).getByText('Nháp')).toBeInTheDocument()
  expect(screen.queryByText('Ưu đãi công nghệ tháng 10')).not.toBeInTheDocument()
})

test('incomplete directory reads fail visibly; retry returns the complete list', async () => {
  articles = Array.from({ length: 101 }, (_, i) => ({ ...article, NewsArticleId: 'a' + i }))
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/news' && args[2].page === 2 && failed ? Promise.reject(new Error('Lỗi trang thứ hai.')) : original(...args))
  renderPage()
  await screen.findByText('Lỗi trang thứ hai.')
  expect(screen.queryByText('101 bài viết')).not.toBeInTheDocument()
  failed = false; fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('101 bài viết')
})

test('create and edit whitelist content fields; new items are drafts and edits preserve publication metadata', async () => {
  const router = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '+ Thêm tin tức' }))
  const dialog = await screen.findByRole('region', { name: 'Thêm tin tức' })
  expect(router.state.location.pathname).toBe('/admin/news/new')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Tin tức', exact: true })).toHaveAttribute('aria-current', 'page')
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Bài mới' } })
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Nội dung' }), { target: { value: 'Nội dung mới' } })
  expect(within(dialog).getByRole('textbox', { name: 'Slug' })).toHaveValue('bai-moi')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu tin tức' }))
  await waitFor(() => expect(api.createNews).toHaveBeenCalledWith('access-for-test', { Title: 'Bài mới', Slug: 'bai-moi', Summary: null, Content: 'Nội dung mới', ThumbnailUrl: null }))
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa Bài mới' }))
  const edit = await screen.findByRole('region', { name: 'Sửa tin tức' })
  expect(router.state.location.pathname).toBe('/admin/news/new/edit')
  fireEvent.change(await within(edit).findByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Tên đã sửa' } })
  fireEvent.click(within(edit).getByRole('button', { name: 'Cập nhật' }))
  await waitFor(() => expect(api.updateNews).toHaveBeenCalledWith('access-for-test', 'new', expect.objectContaining({ Title: 'Tên đã sửa', Slug: 'bai-moi' })))
  expect(api.updateNews.mock.calls[0][2]).not.toHaveProperty('Status')
  expect(api.updateNews.mock.calls[0][2]).not.toHaveProperty('CreatedByUserId')
})

test('delete confirmation cancels without writes; failures retry while pending requests block repeated confirmation', async () => {
  articles = [article]
  const router = renderPage('/admin/news?keyword=tin-tu')
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa ' + article.Title }))
  let dialog = screen.getByRole('dialog', { name: 'Xóa tin tức?' })
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Hủy' }))
  expect(api.deleteNews).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Xóa ' + article.Title }))
  dialog = screen.getByRole('dialog', { name: 'Xóa tin tức?' })
  api.deleteNews.mockRejectedValueOnce(new Error('Chưa xóa được bài.'))
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Xác nhận xóa' }))
  await within(dialog).findByText('Chưa xóa được bài.')
  let finish
  api.deleteNews.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const confirm = within(dialog).getByRole('button', { name: 'Xác nhận xóa' })
  fireEvent.click(confirm); fireEvent.click(confirm)
  expect(api.deleteNews).toHaveBeenCalledTimes(2)
  expect(within(dialog).getByRole('button', { name: 'Hủy' })).toBeDisabled()
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  expect(dialog).toBeInTheDocument()
  await act(async () => { articles = []; finish() })
  await screen.findByText('Không có tin tức phù hợp.')
  expect(router.state.location.search).toBe('?keyword=tin-tu')
})

test('view-only deep links cannot open write dialogs or invoke a write', async () => {
  articles = [article]
  const router = renderPage('/admin/news?dialog=delete&article=a1', ['admin.portal', 'news:view'])
  await screen.findByText('1 bài viết')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '+ Thêm tin tức' })).not.toBeInTheDocument()
  for (const mode of ['edit', 'new']) { await act(() => router.navigate('/admin/news?dialog=' + mode + '&article=a1')); expect(screen.queryByRole('dialog')).not.toBeInTheDocument() }
  fireEvent.click(screen.getByRole('button', { name: 'Xem ' + article.Title }))
  const dialog = await screen.findByRole('region', { name: 'Chi tiết tin tức' })
  await within(dialog).findByDisplayValue(article.Content)
  expect(router.state.location.pathname).toBe('/admin/news/a1')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: 'Sửa tin tức' })).not.toBeInTheDocument()
  expect(api.deleteNews).not.toHaveBeenCalled()
})

test('publishing and hiding use workflow endpoints and preserve the server date', async () => {
  articles = [{ ...article, Status: 'Hidden' }]
  renderPage('/admin/news?dialog=view&article=a1')
  const dialog = await screen.findByRole('region', { name: 'Chi tiết tin tức' })
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Đăng bài viết' }))
  await waitFor(() => expect(api.publishNews).toHaveBeenCalledWith('access-for-test', 'a1'))
  await screen.findByText('Đã đăng tin tức.')
  expect(articles[0].Status).toBe('Published')
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Ẩn bài viết' }))
  await waitFor(() => expect(api.hideNews).toHaveBeenCalledWith('access-for-test', 'a1'))
  expect(articles[0].PublishedAt).toBe(article.PublishedAt)
})

test('dedicated detail/edit pages reload directly, keep sidebar and preserve list filters when closing', async () => {
  articles = [article]
  const router = renderPage('/admin/news/a1?keyword=tin-tu&page=2')
  const detail = await screen.findByRole('region', { name: 'Chi tiết tin tức' })
  await within(detail).findByDisplayValue(article.Content)
  expect(within(detail).getByRole('textbox', { name: 'Thời điểm đăng' })).toHaveValue('12/10/2026 08:30')
  expect(within(detail).getByRole('textbox', { name: 'Tiêu đề' })).toHaveAttribute('readonly')
  expect(screen.getByRole('heading', { level: 1, name: 'Chi tiết tin tức' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Tin tức & Banner' })).toHaveAttribute('aria-expanded', 'true')
  fireEvent.click(within(detail).getByRole('button', { name: 'Sửa tin tức' }))
  const editor = await screen.findByRole('region', { name: 'Sửa tin tức' })
  expect(router.state.location.pathname).toBe('/admin/news/a1/edit')
  expect(within(editor).getAllByRole('option').map((item) => item.value)).toEqual(['Published', 'Hidden'])
  fireEvent.click(within(editor).getByRole('button', { name: 'Hủy' }))
  await screen.findByRole('heading', { level: 1, name: 'Quản lý tin tức' })
  expect(router.state.location.pathname).toBe('/admin/news')
  expect(router.state.location.search).toContain('keyword=tin-tu')
  expect(api.updateNews).not.toHaveBeenCalled()
})

test('update failures overlay the editor, preserve the draft and allow retry without closing the page', async () => {
  articles = [article]
  const router = renderPage('/admin/news/a1/edit')
  const editor = within(await screen.findByRole('region', { name: 'Sửa tin tức' }))
  fireEvent.change(editor.getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Nội dung chưa mất' } })
  api.updateNews.mockRejectedValueOnce(new Error('Slug đã tồn tại.'))
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  const error = await screen.findByRole('dialog', { name: 'Không thể cập nhật tin tức' })
  expect(within(error).getByText('Hệ thống gặp lỗi khi thay đổi dữ liệu. Dữ liệu cũ được giữ nguyên.')).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/admin/news/a1/edit')
  expect(articles[0].Title).toBe(article.Title)
  fireEvent.click(within(error).getByRole('button', { name: 'Đóng thông báo' }))
  expect(editor.getByRole('textbox', { name: 'Tiêu đề' })).toHaveValue('Nội dung chưa mất')
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  await screen.findByText('Đã cập nhật tin tức.')
  expect(api.updateNews).toHaveBeenCalledTimes(2)
})

test('status-only changes use workflow APIs and never send client timestamps or Status in PATCH', async () => {
  articles = [article]
  renderPage('/admin/news/a1/edit')
  const editor = within(await screen.findByRole('region', { name: 'Sửa tin tức' }))
  fireEvent.change(editor.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'Hidden' } })
  fireEvent.click(editor.getByRole('button', { name: 'Cập nhật' }))
  await screen.findByText('Đã cập nhật tin tức.')
  expect(api.hideNews).toHaveBeenCalledWith('access-for-test', 'a1')
  expect(api.updateNews).not.toHaveBeenCalled()
  expect(articles[0].PublishedAt).toBe(article.PublishedAt)
})

test('a publish failure after create reports the saved draft and retries publication without creating duplicates', async () => {
  renderPage('/admin/news/new')
  const editor = within(await screen.findByRole('region', { name: 'Thêm tin tức' }))
  fireEvent.change(editor.getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Bài đăng mới' } })
  fireEvent.change(editor.getByRole('textbox', { name: 'Nội dung' }), { target: { value: 'Đã viết xong' } })
  fireEvent.change(editor.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'Published' } })
  api.publishNews.mockRejectedValueOnce(new Error('Chưa đăng được.'))
  fireEvent.click(editor.getByRole('button', { name: 'Lưu tin tức' }))
  const error = await screen.findByRole('dialog', { name: 'Không thể lưu tin tức' })
  expect(within(error).getByText('Nội dung đã được lưu, nhưng chưa đổi được trạng thái. Bạn có thể thử lại mà không tạo thêm bài viết.')).toBeInTheDocument()
  expect(articles).toHaveLength(1)
  fireEvent.click(within(error).getByRole('button', { name: 'Đóng thông báo' }))
  fireEvent.click(editor.getByRole('button', { name: 'Lưu tin tức' }))
  await screen.findByText('Đã thêm tin tức.')
  expect(api.createNews).toHaveBeenCalledTimes(1)
  expect(api.publishNews).toHaveBeenCalledTimes(2)
  expect(articles[0].Status).toBe('Published')
})

test('local image upload blocks save/cancel until ready and only the uploaded URL is saved', async () => {
  renderPage('/admin/news/new')
  const editor = within(await screen.findByRole('region', { name: 'Thêm tin tức' }))
  fireEvent.change(editor.getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Bài có ảnh' } })
  fireEvent.change(editor.getByRole('textbox', { name: 'Nội dung' }), { target: { value: 'Nội dung có ảnh' } })
  expect(editor.queryByRole('textbox', { name: /URL|Ảnh đại diện/ })).not.toBeInTheDocument()
  let finish
  api.uploadProductImage.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const file = new File(['image-for-test'], 'news.png', { type: 'image/png' })
  fireEvent.change(editor.getByLabelText('Tải ảnh tin tức'), { target: { files: [file] } })
  expect(editor.getByRole('button', { name: 'Hủy' })).toBeDisabled()
  expect(editor.getByRole('button', { name: 'Lưu tin tức' })).toBeDisabled()
  await act(() => finish({ ImageUrl: 'https://storage.example.test/news.png' }))
  fireEvent.click(editor.getByRole('button', { name: 'Lưu tin tức' }))
  await waitFor(() => expect(api.createNews).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ ThumbnailUrl: 'https://storage.example.test/news.png' })))
})

test('write requests guard repeat clicks and missing details cannot create an empty edit form', async () => {
  articles = [article]
  const router = renderPage('/admin/news/a1/edit')
  const editor = within(await screen.findByRole('region', { name: 'Sửa tin tức' }))
  fireEvent.change(editor.getByRole('textbox', { name: 'Tiêu đề' }), { target: { value: 'Đang lưu' } })
  let finish
  api.updateNews.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const save = editor.getByRole('button', { name: 'Cập nhật' })
  fireEvent.click(save); fireEvent.click(save)
  expect(api.updateNews).toHaveBeenCalledTimes(1)
  expect(editor.getByRole('button', { name: 'Hủy' })).toBeDisabled()
  await act(() => finish({ ...article, Title: 'Đang lưu' }))
  await screen.findByText('Đã cập nhật tin tức.')
  await act(() => router.navigate('/admin/news/missing/edit'))
  await screen.findByText('Không tìm thấy bài viết.')
  expect(screen.queryByRole('textbox', { name: 'Tiêu đề' })).not.toBeInTheDocument()
})

test('legacy content bookmarks redirect and banner-only permissions still expose the group', async () => {
  const router = renderPage('/admin/content?tab=1', ['admin.portal', 'banners:view'])
  await screen.findByRole('heading', { level: 1, name: 'Quản lý banner quảng cáo' })
  expect(router.state.location.pathname).toBe('/admin/banners')
  const menu = within(screen.getByRole('navigation', { name: 'Menu quản trị' }))
  expect(menu.getByRole('button', { name: 'Tin tức & Banner' })).toHaveAttribute('aria-expanded', 'true')
  expect(menu.queryByRole('button', { name: 'Tin tức', exact: true })).not.toBeInTheDocument()
})
