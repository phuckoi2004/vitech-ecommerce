import { StrictMode } from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { getNews, listNews, recordNewsView } from '../../lib/catalog-api.js'
import NewsPage from './NewsPage.jsx'

vi.mock('../../lib/catalog-api.js', () => ({ getNews: vi.fn(), listNews: vi.fn(), recordNewsView: vi.fn() }))

const article = {
  NewsArticleId: 'n1', Slug: 'chon-dien-thoai', Title: 'Chọn điện thoại phù hợp',
  Summary: 'Chọn theo nhu cầu và ngân sách.', PublishedAt: '2026-10-17T07:00:00Z',
  ThumbnailUrl: 'https://example.test/cover.jpg',
  ViewCount: 7,
  Content: '<p><strong>Lời mở đầu bài viết.</strong></p><p>Bài viết đối chiếu thông số công bố của <a href="https://example.test/oppo">OPPO</a> và Galaxy để giúp bạn chọn mua.</p>'
    + '<h2>1. Màn hình</h2><p>Nội dung <strong>quan trọng</strong>.</p>'
    + '<p><strong><span style="font-size:20px">2. Pin và sạc</span></strong></p><p>Lựa chọn phù hợp.</p>',
}

function openPage(path = `/tin-tuc/${article.Slug}`, { strict = false } = {}) {
  const router = createMemoryRouter([
    { path: '/tin-tuc', element: <NewsPage /> },
    { path: '/tin-tuc/:slug', element: <NewsPage /> },
  ], { initialEntries: [path] })
  render(strict ? <StrictMode><RouterProvider router={router} /></StrictMode> : <RouterProvider router={router} />)
  return router
}

beforeEach(() => {
  getNews.mockReset().mockResolvedValue(article)
  listNews.mockReset().mockResolvedValue({ Items: [article], Total: 1 })
  recordNewsView.mockReset().mockResolvedValue({ ViewCount: 8 })
})

test('article preserves saved formatting and safe images with the Figma news sidebar', async () => {
  getNews.mockResolvedValue({ ...article, Content: article.Content
    + '<img src="https://example.test/inline.jpg" alt="Ảnh minh họa" onerror="alert(1)"><script>alert(1)</script>' })
  openPage()
  const page = await screen.findByRole('article')
  expect(within(page).getByRole('heading', { level: 1, name: article.Title })).toBeInTheDocument()
  expect(within(page).getByRole('button', { name: 'Tư vấn ngay' })).toBeInTheDocument()
  expect(within(page).getByRole('img', { name: 'VieTech' })).toHaveAttribute('src', expect.stringContaining('vietech-wordmark.png'))
  expect(screen.queryByText('Tin tức · Đánh giá · Tư vấn công nghệ')).not.toBeInTheDocument()
  expect(within(page).getByText(article.Summary)).toBeInTheDocument()
  expect(within(page).getByText('17/10/2026')).toHaveAttribute('datetime', article.PublishedAt)
  expect(within(page).getByRole('img', { name: article.Title })).toHaveAttribute('src', article.ThumbnailUrl)
  expect(within(page).getByRole('heading', { name: '1. Màn hình' })).toBeInTheDocument()
  expect(within(page).getByRole('heading', { name: '2. Pin và sạc' }).querySelector('span')).toHaveStyle({ fontSize: '20px' })
  const contents = screen.getByRole('navigation', { name: 'Mục lục bài viết' })
  const introduction = within(page).getByText(/Bài viết đối chiếu thông số công bố/)
  expect(introduction.parentElement.nextElementSibling).toBe(contents.closest('details'))
  expect(contents.closest('details').nextElementSibling.querySelector('h2')).toHaveTextContent('1. Màn hình')
  const links = within(contents).getAllByRole('link')
  expect(links.map(link => link.textContent)).toEqual(['1. Màn hình', '2. Pin và sạc'])
  const target = within(page).getByRole('heading', { name: '2. Pin và sạc' })
  expect(links[1]).toHaveAttribute('href', `#${target.id}`)
  await userEvent.click(links[1])
  expect(target).toHaveFocus()
  await userEvent.click(screen.getByText('Mục lục bài viết', { selector: 'summary' }))
  expect(contents.closest('details')).not.toHaveAttribute('open')
  expect(within(screen.getByRole('complementary', { name: 'Tin tức liên quan' }))
    .getByRole('link', { name: '← Quay lại Tin tức' })).toHaveAttribute('href', '/tin-tuc')
  expect(page.querySelector('script, [onerror]')).toBeNull()
  expect(within(page).getByRole('img', { name: 'Ảnh minh họa' })).toHaveAttribute('src', 'https://example.test/inline.jpg')
  expect(screen.queryByText(/Chia sẻ bài viết/)).not.toBeInTheDocument()
})

test('short plain-text articles omit empty cover, contents and suggestions', async () => {
  getNews.mockResolvedValue({ ...article, ThumbnailUrl: null, Content: 'Nội dung cũ.\n\nĐoạn tiếp theo.' })
  openPage()
  const page = await screen.findByRole('article')
  expect(within(page).getByText('Nội dung cũ.')).toBeInTheDocument()
  expect(within(page).getByText('Đoạn tiếp theo.')).toBeInTheDocument()
  await waitFor(() => expect(listNews).toHaveBeenCalled())
  expect(screen.queryByRole('navigation', { name: 'Mục lục bài viết' })).not.toBeInTheDocument()
  expect(within(page).queryByRole('img')).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Có thể bạn quan tâm' })).not.toBeInTheDocument()
})

test('consultation opens a modal dialog and supports cancel, close and backdrop dismissal', async () => {
  const user = userEvent.setup()
  const router = openPage()
  const trigger = await screen.findByRole('button', { name: 'Tư vấn ngay' })
  expect(trigger).toHaveAttribute('aria-haspopup', 'dialog')
  expect(screen.queryByRole('dialog', { name: 'Chọn hình thức tư vấn' })).not.toBeInTheDocument()
  await user.click(trigger)
  const dialog = screen.getByRole('dialog', { name: 'Chọn hình thức tư vấn' })
  expect(dialog).toHaveAttribute('open')
  expect(dialog).toHaveAttribute('aria-modal', 'true')
  expect(screen.getByRole('button', { name: 'Chat với nhân viên' })).toHaveFocus()
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  expect(screen.queryByRole('dialog', { name: 'Chọn hình thức tư vấn' })).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
  await user.click(trigger)
  await user.click(screen.getByRole('button', { name: 'Đóng lựa chọn tư vấn' }))
  expect(screen.queryByRole('dialog', { name: 'Chọn hình thức tư vấn' })).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
  await user.click(trigger)
  await user.click(screen.getByRole('dialog', { name: 'Chọn hình thức tư vấn' }))
  expect(screen.queryByRole('dialog', { name: 'Chọn hình thức tư vấn' })).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
  expect(router.state.location.pathname).toBe(`/tin-tuc/${article.Slug}`)
})

test('suggestions exclude the current article and duplicates and do not repeat between the two sections', async () => {
  const next = { ...article, NewsArticleId: 'n2', Slug: 'bai-tiep-theo', Title: 'Tư vấn chọn laptop', Content: '<h2>Cấu hình</h2><p>Nội dung mới.</p><h2>Ngân sách</h2>' }
  const third = { ...article, NewsArticleId: 'n3', Slug: 'bai-ba', Title: 'Chọn màn hình' }
  const fourth = { ...article, NewsArticleId: 'n4', Slug: 'bai-bon', Title: 'Chọn phụ kiện' }
  listNews.mockResolvedValue({ Items: [article, next, next, third, fourth, { ...fourth, Slug: 'bai-nam', Title: 'Không hiển thị' }] })
  getNews.mockImplementation(slug => Promise.resolve(slug === next.Slug ? next : article))
  const router = openPage()
  const more = await screen.findByRole('region', { name: 'Có thể bạn quan tâm' })
  const sidebar = screen.getByRole('complementary', { name: 'Tin tức liên quan' })
  expect(within(sidebar).getAllByRole('listitem')).toHaveLength(1)
  expect(within(more).getAllByRole('listitem')).toHaveLength(2)
  expect(within(sidebar).getByRole('heading', { name: next.Title })).toBeInTheDocument()
  expect(within(more).queryByRole('heading', { name: next.Title })).not.toBeInTheDocument()
  expect(within(more).queryByRole('heading', { name: article.Title })).not.toBeInTheDocument()
  expect(within(more).queryByText('Không hiển thị')).not.toBeInTheDocument()
  await userEvent.click(within(sidebar).getByRole('link', { name: /Tư vấn chọn laptop/ }))
  expect(await screen.findByRole('heading', { level: 1, name: next.Title })).toBeInTheDocument()
  expect(router.state.location.pathname).toBe(`/tin-tuc/${next.Slug}`)
  expect(screen.queryByRole('heading', { name: '1. Màn hình' })).not.toBeInTheDocument()
  expect(within(screen.getByRole('article')).getByRole('heading', { name: 'Cấu hình' })).toBeInTheDocument()
  await act(async () => router.navigate('/tin-tuc'))
  expect(await screen.findByRole('heading', { level: 1, name: 'Tin tức công nghệ' })).toBeInTheDocument()
})

test('failed suggestions stay retryable without hiding the article', async () => {
  listNews.mockRejectedValueOnce(new Error('Kết nối bị gián đoạn.'))
  openPage()
  const failure = await screen.findByRole('alert')
  expect(within(failure).getByText('Kết nối bị gián đoạn.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 1, name: article.Title })).toBeInTheDocument()
  await userEvent.click(within(failure).getByRole('button', { name: 'Thử lại' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(listNews).toHaveBeenCalledTimes(2)
  expect(screen.getByRole('article')).toBeInTheDocument()
})

test('duplicate section names get distinct safe anchors and bold body text stays outside the contents', async () => {
  getNews.mockResolvedValue({ ...article, Content: '<p><strong>Lưu ý khi chọn máy.</strong></p>'
    + '<h2 id="unsafe" onclick="alert(1)">Cấu hình</h2><p>Nội dung đầu.</p>'
    + '<h2 id="unsafe">Cấu hình</h2><p>Nội dung tiếp.</p>' })
  openPage()
  const contents = await screen.findByRole('navigation', { name: 'Mục lục bài viết' })
  const links = within(contents).getAllByRole('link')
  expect(links).toHaveLength(2)
  expect(new Set(links.map(link => link.getAttribute('href'))).size).toBe(2)
  const headings = within(screen.getByRole('article')).getAllByRole('heading', { name: 'Cấu hình' })
  for (let index = 0; index < headings.length; index++) {
    expect(links[index]).toHaveAttribute('href', `#${headings[index].id}`)
    expect(headings[index]).not.toHaveAttribute('onclick')
    expect(headings[index]).not.toHaveAttribute('id', 'unsafe')
  }
})

test('one page open counts once in StrictMode and another visit counts again', async () => {
  let count = article.ViewCount
  recordNewsView.mockImplementation(() => Promise.resolve({ ViewCount: ++count }))
  const router = openPage(undefined, { strict: true })
  expect(await screen.findByText('8 lượt xem')).toBeInTheDocument()
  expect(recordNewsView).toHaveBeenCalledExactlyOnceWith(article.Slug)
  await act(async () => router.navigate('/tin-tuc'))
  expect(await screen.findByRole('heading', { level: 1, name: 'Tin tức công nghệ' })).toBeInTheDocument()
  expect(recordNewsView).toHaveBeenCalledTimes(1)
  await act(async () => router.navigate(`/tin-tuc/${article.Slug}`))
  expect(await screen.findByText('9 lượt xem')).toBeInTheDocument()
  expect(recordNewsView).toHaveBeenCalledTimes(2)
})

test('counting being unavailable keeps the saved total and does not prevent reading', async () => {
  getNews.mockResolvedValue({ ...article, ViewCount: 1234 })
  recordNewsView.mockRejectedValue(new Error('Không kết nối được máy chủ.'))
  openPage()
  expect(await screen.findByText('1.234 lượt xem')).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 1, name: article.Title })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
