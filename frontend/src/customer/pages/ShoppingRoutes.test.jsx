import { StrictMode } from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { appRoutes } from '../../routes.jsx'
import { makeAuth } from '../../test/auth.js'

const product = {
  ProductId: 'p1', Name: 'Điện thoại mẫu', Slug: 'dien-thoai-mau', BrandId: 'b1', CategoryId: 'child', Status: 'Active',
  AverageRating: '4.5', ReviewCount: 3, SoldQuantity: 20, WarrantyMonths: 12, Description: 'Mô tả sản phẩm.',
  Brand: { Name: 'Apple' }, Category: { Name: 'Điện thoại' }, Images: [],
  Variants: [{ ProductVariantId: 'v1', VariantName: '256GB', Price: '10000000.00', StockQuantity: 3 }],
}
const conversation = { ConversationId: 'c1', Mode: 'Staff', Status: 'Open', CreatedAt: '2026-10-13T00:00:00Z', ClosedAt: null }

function mockApi({ existingConversation = null, messages = [], history = [], newsContent = 'Nội dung bài viết.' } = {}) {
  const calls = []
  const records = [...history]
  if (existingConversation) records.unshift({ ...existingConversation })
  const threads = new Map([['c1', messages], ...history.map(item => [item.ConversationId, item.Messages ?? []])])
  let nextId = 1
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost')
    const endpoint = url.pathname.replace(/^\/api/, '')
    const method = options.method ?? 'GET'
    const body = options.body ? JSON.parse(options.body) : null
    calls.push({ endpoint, method, body, query: Object.fromEntries(url.searchParams), token: options.headers?.Authorization })
    let result, status = 200
    if (endpoint === '/categories' || endpoint === '/banners') result = []
    else if (endpoint === '/brands') result = [{ BrandId: 'b1', Name: 'Apple', Slug: 'apple' }]
    else if (endpoint === '/categories/slug/dien-thoai') result = { CategoryId: 'root', Name: 'Điện thoại', Slug: 'dien-thoai' }
    else if (endpoint === '/brands/slug/apple') result = { BrandId: 'b1', Name: 'Apple', Slug: 'apple' }
    else if (endpoint === '/products') result = { Items: [product], Total: 1, Page: 1, PageSize: 20 }
    else if (endpoint === '/products/p1' || endpoint === '/products/slug/dien-thoai-mau') result = product
    else if (endpoint === '/products/p1/reviews') result = { Items: [], Total: 0, Page: Number(url.searchParams.get('page')), PageSize: Number(url.searchParams.get('page_size')) }
    else if (endpoint === '/cart/items') result = { Items: [], SelectedQuantity: 0, SelectedSubtotal: '0.00' }
    else if (endpoint === '/cart') result = { Items: [], SelectedQuantity: 0, SelectedSubtotal: '0.00' }
    else if (endpoint === '/wishlist') result = { Items: [] }
    else if (endpoint === '/users/me/notifications') result = { Items: [], Total: 0 }
    else if (endpoint === '/users/me/notifications/unread-count') result = { Count: 0 }
    else if (endpoint === '/news') result = { Items: [{ NewsArticleId: 'n1', Title: 'Tin công nghệ', Slug: 'tin-cong-nghe' }], Total: 1 }
    else if (endpoint === '/news/tin-cong-nghe') result = { Title: 'Tin công nghệ', Content: newsContent }
    else if (endpoint === '/conversations' && method === 'POST') {
      while (records.some(item => item.ConversationId === `c${nextId}`)) nextId++
      result = { ...conversation, ConversationId: `c${nextId}`, CreatedAt: new Date(Date.parse(conversation.CreatedAt) + nextId * 60000).toISOString() }
      records.unshift(result); if (!threads.has(result.ConversationId)) threads.set(result.ConversationId, []); nextId++
    }
    else if (endpoint === '/conversations') {
      const items = records.filter(item => !url.searchParams.has('status') || item.Status === url.searchParams.get('status'))
      const page = Number(url.searchParams.get('page') || 1), size = Number(url.searchParams.get('page_size') || 20)
      result = { Items: items.slice((page - 1) * size, page * size), Total: items.length, Page: page, PageSize: size }
    }
    else if (/^\/conversations\/[^/]+$/.test(endpoint)) {
      const id = endpoint.split('/')[2]
      result = { ...records.find(item => item.ConversationId === id), Messages: [...(threads.get(id) ?? [])] }
    }
    else if (/^\/conversations\/[^/]+\/close$/.test(endpoint)) {
      result = records.find(item => item.ConversationId === endpoint.split('/')[2]); result.Status = 'Closed'
    }
    else if (/^\/conversations\/[^/]+\/messages$/.test(endpoint)) {
      const id = endpoint.split('/')[2], thread = threads.get(id)
      const message = { MessageId: `m-${id}-${thread.length}`, ...body, SenderType: 'Customer', SentAt: '2026-10-13T01:00:00Z' }
      thread.push(message); result = message
    } else { status = 404; result = { detail: 'Không tìm thấy' } }
    return new Response(JSON.stringify(result), { status, headers: { 'Content-Type': 'application/json' } })
  }))
  return calls
}

function renderAt(url, auth = makeAuth(), { strict = false } = {}) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [url] })
  const app = <AuthContext.Provider value={auth}><RouterProvider router={router} /></AuthContext.Provider>
  render(strict ? <StrictMode>{app}</StrictMode> : app)
  return router
}

afterEach(() => vi.unstubAllGlobals())

test('price filter combines with brand and keyword, resets pagination and can be cleared', async () => {
  const calls = mockApi()
  const router = renderAt('/danh-muc/dien-thoai?brand=b1&q=mau&page=3&price=5-10')
  const prices = await screen.findByRole('combobox', { name: 'Khoảng giá' })
  expect(prices).toHaveValue('5-10')
  await waitFor(() => expect(calls.filter((call) => call.endpoint === '/products').at(-1).query).toMatchObject({
    category_id: 'root', brand_id: 'b1', keyword: 'mau', page: '3', min_price: '5000000', max_price: '9999999.99',
  }))
  fireEvent.change(prices, { target: { value: 'from-20' } })
  await waitFor(() => expect(calls.filter((call) => call.endpoint === '/products').at(-1).query).toMatchObject({
    brand_id: 'b1', keyword: 'mau', page: '1', min_price: '20000000',
  }))
  expect(new URLSearchParams(router.state.location.search).has('page')).toBe(false)
  expect(calls.filter((call) => call.endpoint === '/products').at(-1).query).not.toHaveProperty('max_price')
  fireEvent.change(prices, { target: { value: '' } })
  await waitFor(() => expect(calls.filter((call) => call.endpoint === '/products').at(-1).query).not.toHaveProperty('min_price'))
  expect(calls.filter((call) => call.endpoint === '/products').at(-1).query).toMatchObject({ brand_id: 'b1', keyword: 'mau' })
})

test.each([
  ['/tim-kiem?q=iphone', 'Kết quả tìm kiếm: iphone'],
  ['/danh-muc/dien-thoai', 'Điện thoại'],
  ['/thuong-hieu/apple', 'Apple'],
])('catalog destination %s renders real results instead of 404', async (url, heading) => {
  const calls = mockApi()
  renderAt(url)
  expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: product.Name })).toBeInTheDocument()
  if (url.includes('danh-muc')) expect(calls.find(c => c.endpoint === '/products').query).toMatchObject({ category_id: 'root', include_descendants: 'true' })
  if (url.includes('thuong-hieu')) expect(calls.find(c => c.endpoint === '/products').query.brand_id).toBe('b1')
})

test('product page adds the selected variant through the authenticated cart API', async () => {
  const calls = mockApi()
  const user = userEvent.setup()
  renderAt('/san-pham/dien-thoai-mau', makeAuth({ role: 'Customer' }))
  await user.click(await screen.findByRole('button', { name: 'Thêm vào giỏ hàng' }))
  expect(await screen.findByText('Đã thêm vào giỏ hàng.')).toBeInTheDocument()
  expect(calls.find(c => c.endpoint === '/cart/items')).toMatchObject({ method: 'POST', body: { ProductVariantId: 'v1', Quantity: 1 }, token: 'Bearer access-for-test' })
})

test.each([
  ['/gio-hang', 'Giỏ hàng đang trống'], ['/yeu-thich', 'Bạn chưa có sản phẩm yêu thích nào.'],
  ['/thong-bao', 'Chưa có thông báo'], ['/tin-tuc', 'Tin tức công nghệ'],
  ['/tin-tuc/tin-cong-nghe', 'Tin công nghệ'],
])('home destination %s renders its page', async (url, heading) => {
  mockApi()
  renderAt(url, makeAuth({ role: 'Customer' }))
  expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Không tìm thấy trang' })).not.toBeInTheDocument()
})

test('news displays saved formatting and inline images while removing unsafe HTML', async () => {
  mockApi({ newsContent: '<p><strong>Nội dung định dạng</strong></p><ul><li>Tiêu chí chọn máy</li></ul><img src="https://cdn.example.test/news.png" alt="Ảnh bài viết" onerror="alert(1)"><script>alert(1)</script>' })
  renderAt('/tin-tuc/tin-cong-nghe')
  const content = await screen.findByText('Nội dung định dạng')
  expect(content.tagName).toBe('STRONG')
  expect(screen.getByText('Tiêu chí chọn máy').closest('ul')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: 'Ảnh bài viết' })).toHaveAttribute('src', 'https://cdn.example.test/news.png')
  const article = screen.getByRole('article')
  expect(article.querySelector('script')).toBeNull()
  expect(article.querySelector('[onerror]')).toBeNull()
})

test('chat requires customer sign-in and preserves the return URL', async () => {
  const calls = mockApi()
  const router = renderAt('/tu-van')
  expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
  expect(router.state.location.search).toBe('?next=%2Ftu-van')
  expect(calls.some(c => c.endpoint === '/conversations')).toBe(false)
})

test('opening chat starts Staff mode immediately and sends a message without spoofing the sender', async () => {
  const calls = mockApi()
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  const box = await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  const composer = screen.getByRole('form', { name: 'Soạn tin nhắn' })
  expect(within(composer).getAllByRole('button')).toHaveLength(1)
  expect(within(composer).getByRole('button', { name: 'Gửi tin nhắn' })).toBeDisabled()
  expect(within(composer).queryByRole('button', { name: 'Dừng hội thoại' })).not.toBeInTheDocument()
  expect(calls.find(c => c.endpoint === '/conversations' && c.method === 'POST').body).toEqual({ Mode: 'Staff' })
  expect(screen.queryByRole('button', { name: 'Bắt đầu chat với nhân viên' })).not.toBeInTheDocument()
  await user.type(box, 'Tôi cần tư vấn laptop')
  await user.clear(box)
  expect(within(composer).getByRole('button', { name: 'Gửi tin nhắn' })).toBeDisabled()
  expect(within(composer).queryByRole('button', { name: 'Dừng hội thoại' })).not.toBeInTheDocument()
  await user.type(box, 'Tôi cần tư vấn laptop')
  expect(within(composer).queryByRole('button', { name: 'Dừng hội thoại' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  expect(await screen.findByText('Tôi cần tư vấn laptop')).toBeInTheDocument()
  expect(within(composer).getByRole('button', { name: 'Dừng hội thoại' })).toBeInTheDocument()
  expect(calls.find(c => c.endpoint.endsWith('/messages')).body).toEqual({ MessageType: 'Text', Content: 'Tôi cần tư vấn laptop' })
})

test('an employee reply restores the send arrow even if the API returns messages out of order', async () => {
  const messages = []
  mockApi({ messages })
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  const box = await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  await user.type(box, 'Tôi cần hỗ trợ')
  await user.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  expect(await screen.findByRole('button', { name: 'Dừng hội thoại' })).toBeEnabled()
  messages.unshift({ MessageId: 'reply1', SenderType: 'Staff', MessageType: 'Text', Content: 'Nhân viên đã tiếp nhận', SentAt: '2026-10-13T02:00:00Z' })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  expect(await screen.findByText('Nhân viên đã tiếp nhận')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Dừng hội thoại' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gửi tin nhắn' })).toBeDisabled()
  await user.type(box, 'Cảm ơn')
  expect(screen.getByRole('button', { name: 'Gửi tin nhắn' })).toBeEnabled()
})

test('Enter sends a message, Shift+Enter adds a line, and an empty Enter never ends the conversation', async () => {
  const calls = mockApi()
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  const box = await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  await user.click(box)
  await user.keyboard('{Enter}')
  expect(calls.some(c => c.endpoint.endsWith('/messages') || c.endpoint.endsWith('/close'))).toBe(false)
  await user.type(box, 'Tôi cần tư vấn')
  await user.keyboard('{Shift>}{Enter}{/Shift}')
  await user.type(box, 'về laptop')
  expect(calls.some(c => c.endpoint.endsWith('/messages'))).toBe(false)
  expect(box).toHaveValue('Tôi cần tư vấn\nvề laptop')
  await user.keyboard('{Enter}')
  expect(await screen.findByText(/Tôi cần tư vấn\s+về laptop/)).toBeInTheDocument()
  expect(calls.filter(c => c.endpoint.endsWith('/messages'))).toHaveLength(1)
  expect(calls.find(c => c.endpoint.endsWith('/messages')).body.Content).toBe('Tôi cần tư vấn\nvề laptop')
  expect(calls.some(c => c.endpoint.endsWith('/close'))).toBe(false)
})

test('chat renders image and product metadata without turning unsafe image URLs into links', async () => {
  mockApi({ existingConversation: conversation, messages: [
    { MessageId: 'photo', SenderType: 'Staff', MessageType: 'Image', Content: 'Ảnh tư vấn', Metadata: { ImageUrl: 'https://example.com/photo.png' }, SentAt: '2026-10-13T01:00:00Z' },
    { MessageId: 'product', SenderType: 'Staff', MessageType: 'Product', Content: '', Metadata: { ProductName: 'Laptop được tư vấn', Slug: 'laptop-tu-van' }, SentAt: '2026-10-13T01:01:00Z' },
    { MessageId: 'unsafe', SenderType: 'Staff', MessageType: 'Image', Content: '', Metadata: { ImageUrl: 'javascript:alert(1)' }, SentAt: '2026-10-13T01:02:00Z' },
  ] })
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  expect(await screen.findByRole('link', { name: 'Xem ảnh đính kèm' })).toHaveAttribute('href', 'https://example.com/photo.png')
  expect(screen.getByRole('img', { name: 'Ảnh tư vấn' })).toHaveAttribute('src', 'https://example.com/photo.png')
  expect(screen.getByRole('link', { name: 'Laptop được tư vấn' })).toHaveAttribute('href', '/san-pham/laptop-tu-van')
  expect(screen.getByText('Ảnh đính kèm không khả dụng.')).toBeInTheDocument()
  expect(document.querySelector('[href^="javascript:"], [src^="javascript:"]')).toBeNull()
})

test('failed message survives polling and retry resends the failed content while preserving a newer draft', async () => {
  const calls = mockApi({ existingConversation: conversation })
  const fetchApi = globalThis.fetch
  let fail = true, attempts = 0
  vi.stubGlobal('fetch', vi.fn((input, options) => {
    if (String(input).endsWith('/messages') && options?.method === 'POST') {
      attempts++
      if (fail) return Promise.resolve(new Response(JSON.stringify({ detail: 'Không gửi được tin nhắn.' }), { status: 503 }))
    }
    return fetchApi(input, options)
  }))
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  const box = await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  await user.type(box, 'Tin nhắn gửi lỗi')
  await user.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Không gửi được tin nhắn.')
  const previousReads = calls.filter(call => call.endpoint === '/conversations/c1').length
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  await waitFor(() => expect(calls.filter(call => call.endpoint === '/conversations/c1').length).toBeGreaterThan(previousReads))
  expect(screen.getByRole('alert')).toHaveTextContent('Không gửi được tin nhắn.')
  expect(box).toHaveValue('Tin nhắn gửi lỗi')
  await user.clear(box)
  await user.type(box, 'Bản nháp mới')
  fail = false
  await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText('Tin nhắn gửi lỗi', { exact: true })).toBeInTheDocument()
  expect(attempts).toBe(2)
  expect(calls.find(call => call.endpoint.endsWith('/messages')).body.Content).toBe('Tin nhắn gửi lỗi')
  expect(box).toHaveValue('Bản nháp mới')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('retrying a close failure actually closes the conversation', async () => {
  mockApi({ existingConversation: conversation, messages: [{ MessageId: 'sent', SenderType: 'Customer', MessageType: 'Text', Content: 'Cần hỗ trợ', SentAt: '2026-10-13T01:00:00Z' }] })
  const fetchApi = globalThis.fetch
  let attempts = 0
  vi.stubGlobal('fetch', vi.fn((input, options) => {
    if (String(input).endsWith('/close') && ++attempts === 1) return Promise.resolve(new Response(JSON.stringify({ detail: 'Chưa kết thúc được hội thoại.' }), { status: 503 }))
    return fetchApi(input, options)
  }))
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await user.click(await screen.findByRole('button', { name: 'Dừng hội thoại' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Chưa kết thúc được hội thoại.')
  await user.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText('Hội thoại đã kết thúc')).toBeInTheDocument()
  expect(attempts).toBe(2)
})

test('incoming messages preserve the reading position and follow the end only when already near it', async () => {
  const messages = [{ MessageId: 'first', SenderType: 'Staff', MessageType: 'Text', Content: 'Tin cũ', SentAt: '2026-10-13T01:00:00Z' }]
  mockApi({ existingConversation: conversation, messages })
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await screen.findByText('Tin cũ')
  const log = screen.getByRole('log', { name: 'Tin nhắn' })
  Object.defineProperties(log, { scrollHeight: { configurable: true, value: 2000 }, clientHeight: { configurable: true, value: 300 } })
  log.scrollTop = 100
  fireEvent.scroll(log)
  messages.push({ MessageId: 'second', SenderType: 'Staff', MessageType: 'Text', Content: 'Tin mới thứ nhất', SentAt: '2026-10-13T01:01:00Z' })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  expect(await screen.findByText('Tin mới thứ nhất')).toBeInTheDocument()
  expect(log.scrollTop).toBe(100)
  log.scrollTop = 1700
  fireEvent.scroll(log)
  messages.push({ MessageId: 'third', SenderType: 'Staff', MessageType: 'Text', Content: 'Tin mới thứ hai', SentAt: '2026-10-13T01:02:00Z' })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  expect(await screen.findByText('Tin mới thứ hai')).toBeInTheDocument()
  expect(log.scrollTop).toBe(2000)
})

test('the home page has one employee entry and opens the conversation without leaving the page', async () => {
  const calls = mockApi()
  const user = userEvent.setup()
  const router = renderAt('/', makeAuth({ role: 'Customer' }))
  const employee = screen.getByRole('button', { name: 'Chat với nhân viên', exact: true })
  expect(screen.getAllByRole('button', { name: 'Chat với nhân viên', exact: true })).toHaveLength(1)
  expect(screen.queryByRole('link', { name: 'Chat với nhân viên', exact: true })).not.toBeInTheDocument()
  expect(calls.some(c => c.endpoint === '/conversations')).toBe(false)
  await user.click(employee)
  const dialog = screen.getByRole('dialog', { name: 'Chat với nhân viên' })
  expect(await within(dialog).findByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/')
  expect(calls.filter(c => c.endpoint === '/conversations' && c.method === 'POST')).toHaveLength(1)
  await user.click(within(dialog).getByRole('button', { name: 'Đóng cửa sổ chat' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(employee).toHaveFocus()
  expect(calls.some(c => c.endpoint.endsWith('/close'))).toBe(false)
  await user.click(employee)
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()
  expect(calls.filter(c => c.endpoint === '/conversations' && c.method === 'POST')).toHaveLength(1)
})

test('closing, reopening and switching chat windows preserves the draft until a successful send', async () => {
  mockApi({ existingConversation: conversation })
  const user = userEvent.setup()
  renderAt('/', makeAuth({ role: 'Customer' }))
  const employee = screen.getByRole('button', { name: 'Chat với nhân viên', exact: true })
  await user.click(employee)
  await user.type(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' }), 'Bản nháp cần giữ')
  await user.click(screen.getByRole('button', { name: 'Đóng cửa sổ chat' }))
  await user.click(employee)
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toHaveValue('Bản nháp cần giữ')
  await user.click(screen.getByRole('button', { name: 'Chat với AI', exact: true }))
  await user.click(employee)
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toHaveValue('Bản nháp cần giữ')
  await user.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  expect(await screen.findByText('Bản nháp cần giữ', { exact: true })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Đóng cửa sổ chat' }))
  await user.click(employee)
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toHaveValue('')
})

test('drafts stay with their conversation when browsing history', async () => {
  const old = { ...conversation, ConversationId: 'old1', Status: 'Closed', CreatedAt: '2026-10-12T08:00:00Z' }
  mockApi({ existingConversation: conversation, history: [old] })
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await user.type(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' }), 'Bản nháp hội thoại đang mở')
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  await user.click(await screen.findByRole('button', { name: /Đã kết thúc/ }))
  await screen.findByText('Hội thoại đã kết thúc')
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  await user.click(await screen.findByRole('button', { name: /Đang mở/ }))
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toHaveValue('Bản nháp hội thoại đang mở')
})

test('signing out clears chat drafts even when the same customer signs in again', async () => {
  mockApi({ existingConversation: conversation })
  const router = createMemoryRouter(appRoutes, { initialEntries: ['/'] })
  const auth = makeAuth({ role: 'Customer' })
  const app = (value) => <AuthContext.Provider value={value}><RouterProvider router={router} /></AuthContext.Provider>
  const view = render(app(auth))
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Chat với nhân viên', exact: true }))
  await user.type(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' }), 'Bản nháp riêng tư')
  view.rerender(app(makeAuth()))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  view.rerender(app(auth))
  await user.click(screen.getByRole('button', { name: 'Chat với nhân viên', exact: true }))
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toHaveValue('')
})

test('AI opens a coming-soon window without creating or closing any conversation', async () => {
  const calls = mockApi()
  const user = userEvent.setup()
  renderAt('/')
  const employee = screen.getByRole('button', { name: 'Chat với nhân viên', exact: true })
  const ai = screen.getByRole('button', { name: 'Chat với AI', exact: true })
  expect(employee.compareDocumentPosition(ai) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  await user.click(ai)
  const dialog = screen.getByRole('dialog', { name: 'Chat với AI' })
  expect(within(dialog).getByRole('heading', { name: 'Sắp ra mắt' })).toBeInTheDocument()
  expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
  expect(calls.some(c => c.endpoint.startsWith('/conversations'))).toBe(false)
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(ai).toHaveFocus()
})

test('a guest clicking employee chat signs in before any conversation is opened', async () => {
  const calls = mockApi()
  const user = userEvent.setup()
  const router = renderAt('/')
  await user.click(screen.getByRole('button', { name: 'Chat với nhân viên', exact: true }))
  expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
  expect(router.state.location.search).toBe('?next=%2Ftu-van')
  expect(calls.some(c => c.endpoint.startsWith('/conversations'))).toBe(false)
})

test('an open Staff conversation is reused without creating another one', async () => {
  const calls = mockApi({ existingConversation: conversation })
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()
  expect(calls.filter(c => c.endpoint === '/conversations' && c.method === 'POST')).toHaveLength(0)
})

test('StrictMode opens only one conversation while remounting the initialization effect', async () => {
  const calls = mockApi()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }), { strict: true })
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()
  expect(calls.filter(c => c.endpoint === '/conversations' && c.method === 'POST')).toHaveLength(1)
})

test('closing the conversation does not immediately create another one', async () => {
  const calls = mockApi()
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await user.type(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' }), 'Tôi muốn hỏi về đơn hàng')
  await user.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  await user.click(await screen.findByRole('button', { name: 'Dừng hội thoại' }))
  expect(await screen.findByText('Hội thoại đã kết thúc')).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'Nội dung tin nhắn' })).not.toBeInTheDocument()
  expect(calls.filter(c => c.endpoint === '/conversations' && c.method === 'POST')).toHaveLength(1)
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  await user.click(screen.getByRole('button', { name: 'Tạo hội thoại mới' }))
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()
  expect(calls.filter(c => c.endpoint === '/conversations' && c.method === 'POST')).toHaveLength(2)
})

test('an older AI conversation is only closed when the customer explicitly chooses to switch', async () => {
  const calls = mockApi({ existingConversation: { ...conversation, Mode: 'AI' } })
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await screen.findByText(/Bạn có hội thoại với trợ lý đang mở/)
  expect(calls.some(c => c.method === 'POST')).toBe(false)
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  await user.click(screen.getByRole('button', { name: 'Tạo hội thoại mới' }))
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()
  expect(calls.filter(c => c.endpoint.endsWith('/close'))).toHaveLength(1)
  expect(calls.filter(c => c.endpoint === '/conversations' && c.method === 'POST')).toHaveLength(1)
})

test('the hamburger keeps history and new-chat actions hidden until opened, without losing a draft', async () => {
  mockApi()
  const user = userEvent.setup()
  renderAt('/', makeAuth({ role: 'Customer' }))
  await user.click(screen.getByRole('button', { name: 'Chat với nhân viên', exact: true }))
  const dialog = screen.getByRole('dialog', { name: 'Chat với nhân viên' })
  const box = await within(dialog).findByRole('textbox', { name: 'Nội dung tin nhắn' })
  await user.type(box, 'Tin nhắn đang soạn')
  expect(within(dialog).queryByRole('combobox')).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: 'Tạo hội thoại mới' })).not.toBeInTheDocument()
  const menu = within(dialog).getByRole('button', { name: 'Danh sách hội thoại', exact: true })
  await user.click(menu)
  expect(menu).toHaveAttribute('aria-expanded', 'true')
  expect(within(dialog).getByRole('region', { name: 'Danh sách hội thoại' })).toBeInTheDocument()
  expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(dialog).toBeInTheDocument()
  expect(menu).toHaveAttribute('aria-expanded', 'false')
  expect(within(dialog).getByRole('textbox', { name: 'Nội dung tin nhắn' })).toHaveValue('Tin nhắn đang soạn')
})

test('choosing a closed conversation from the menu reads its messages without reopening it', async () => {
  const old = { ...conversation, ConversationId: 'old1', Status: 'Closed', CreatedAt: '2026-10-12T08:00:00Z',
    Messages: [{ MessageId: 'old-message', SenderType: 'Staff', MessageType: 'Text', Content: 'Tin nhắn của hội thoại cũ', SentAt: '2026-10-12T08:01:00Z' }] }
  const calls = mockApi({ existingConversation: conversation, history: [old] })
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  const history = screen.getByRole('region', { name: 'Danh sách hội thoại' })
  await user.click(await within(history).findByRole('button', { name: /Đã kết thúc/ }))
  expect(await screen.findByText('Tin nhắn của hội thoại cũ')).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(calls.some(call => call.method === 'POST')).toBe(false)
})

test('a notification link opens the exact closed conversation without starting a new one', async () => {
  const old = { ...conversation, ConversationId: 'old-notification', Status: 'Closed', CreatedAt: '2026-10-12T08:00:00Z',
    Messages: [{ MessageId: 'notification-reply', SenderType: 'Staff', MessageType: 'Text', Content: 'Trả lời trong hội thoại từ thông báo', SentAt: '2026-10-12T08:01:00Z' }] }
  const calls = mockApi({ existingConversation: conversation, history: [old] })
  renderAt('/tu-van?conversation=old-notification', makeAuth({ role: 'Customer' }))
  expect(await screen.findByText('Trả lời trong hội thoại từ thông báo')).toBeInTheDocument()
  expect(screen.getByText('Hội thoại đã kết thúc')).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'Nội dung tin nhắn' })).not.toBeInTheDocument()
  expect(calls.some(call => call.method === 'POST')).toBe(false)
})

test('creating a new conversation closes the open one first and preserves its messages in history', async () => {
  const saved = [{ MessageId: 'saved1', SenderType: 'Customer', MessageType: 'Text', Content: 'Nội dung cần giữ lại', SentAt: '2026-10-13T01:00:00Z' }]
  const calls = mockApi({ existingConversation: conversation, messages: saved })
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  await user.click(screen.getByRole('button', { name: 'Tạo hội thoại mới' }))
  const box = await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  expect(box).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Gửi tin nhắn' })).toBeDisabled()
  expect(calls.filter(call => call.method === 'POST').map(call => call.endpoint)).toEqual(['/conversations/c1/close', '/conversations'])
  expect(calls.some(call => call.endpoint === '/conversations/c2')).toBe(true)
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  await user.click(await screen.findByRole('button', { name: /Đã kết thúc/ }))
  expect(await screen.findByText('Nội dung cần giữ lại')).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})

test('a failed new-conversation request keeps the closed history and can be retried', async () => {
  const calls = mockApi({ existingConversation: conversation })
  const fetchApi = globalThis.fetch
  let failing = true
  vi.stubGlobal('fetch', vi.fn((url, options) => String(url).endsWith('/conversations') && options?.method === 'POST' && failing
    ? Promise.resolve(new Response(JSON.stringify({ detail: 'Hệ thống đang bận.' }), { status: 503 })) : fetchApi(url, options)))
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  await user.click(screen.getByRole('button', { name: 'Tạo hội thoại mới' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Hệ thống đang bận.')
  expect(await screen.findByRole('button', { name: /Đã kết thúc/ })).toBeInTheDocument()
  failing = false
  await user.click(screen.getByRole('button', { name: 'Tạo hội thoại mới' }))
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toHaveValue('')
  expect(calls.filter(call => call.endpoint.endsWith('/close'))).toHaveLength(1)
  expect(calls.filter(call => call.endpoint === '/conversations' && call.method === 'POST')).toHaveLength(1)
})

test('the conversation menu supports pages beyond the first twenty records', async () => {
  const old = Array.from({ length: 20 }, (_, index) => ({ ...conversation, ConversationId: `old${index}`, Status: 'Closed', CreatedAt: '2026-10-12T08:00:00Z' }))
  const calls = mockApi({ existingConversation: conversation, history: old })
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  await user.click(await screen.findByRole('button', { name: 'Sau', exact: true }))
  expect(await screen.findByText('Trang 2 / 2')).toBeInTheDocument()
  expect(calls.some(call => call.endpoint === '/conversations' && call.query.page === '2' && call.query.page_size === '20')).toBe(true)
  expect(within(screen.getByRole('region', { name: 'Danh sách hội thoại' })).getAllByRole('button', { name: /Đã kết thúc/ })).toHaveLength(1)
})

test('opening the conversation menu refreshes its status instead of replacing it with the cached open state', async () => {
  mockApi({ existingConversation: conversation })
  const fetchApi = globalThis.fetch
  let closedOnServer = false
  vi.stubGlobal('fetch', vi.fn(async (input, options) => {
    const response = await fetchApi(input, options)
    const url = new URL(input, 'http://localhost')
    if (closedOnServer && url.pathname === '/api/conversations' && url.searchParams.get('page_size') === '20') {
      const body = await response.json()
      return new Response(JSON.stringify({ ...body, Items: body.Items.map(item => ({ ...item, Status: 'Closed' })) }), { status: 200 })
    }
    return response
  }))
  const user = userEvent.setup()
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })
  closedOnServer = true
  await user.click(screen.getByRole('button', { name: 'Danh sách hội thoại', exact: true }))
  const menu = screen.getByRole('region', { name: 'Danh sách hội thoại' })
  expect(await within(menu).findByRole('button', { name: /Đã kết thúc/ })).toBeInTheDocument()
  expect(within(menu).queryByRole('button', { name: /Đang mở/ })).not.toBeInTheDocument()
})

test('an opening failure is displayed and can be retried without an empty conversation view', async () => {
  mockApi()
  const fetchApi = globalThis.fetch
  let failing = true
  vi.stubGlobal('fetch', vi.fn((url, options) => String(url).endsWith('/conversations') && options?.method === 'POST' && failing
    ? Promise.resolve(new Response(JSON.stringify({ detail: 'Hệ thống đang bận.' }), { status: 503 })) : fetchApi(url, options)))
  renderAt('/tu-van', makeAuth({ role: 'Customer' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Hệ thống đang bận.')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  failing = false
  await userEvent.setup().click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()
})

test('a detail 503 shows a retry action instead of claiming there are no products', async () => {
  mockApi()
  const fetchApi = globalThis.fetch
  let failing = true
  vi.stubGlobal('fetch', vi.fn((url, options) => String(url).endsWith('/products/p1') && failing
    ? Promise.resolve(new Response(JSON.stringify({ detail: 'Hệ thống đang bận.' }), { status: 503 })) : fetchApi(url, options)))
  const router = renderAt('/tim-kiem')
  expect(await screen.findByRole('alert')).toHaveTextContent('Hệ thống đang bận.')
  expect(screen.queryByText('Không có sản phẩm phù hợp')).not.toBeInTheDocument()
  failing = false
  await userEvent.setup().click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByRole('heading', { name: product.Name })).toBeInTheDocument()
  await act(async () => router.navigate('/dang-nhap'))
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument())
})
