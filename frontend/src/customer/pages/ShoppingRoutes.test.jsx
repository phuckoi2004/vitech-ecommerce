import { StrictMode } from 'react'
import { act, render, screen, waitFor, within } from '@testing-library/react'
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

function mockApi({ existingConversation = null, messages = [], history = [] } = {}) {
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
    else if (endpoint === '/cart/items') result = { Items: [], SelectedQuantity: 0, SelectedSubtotal: '0.00' }
    else if (endpoint === '/cart') result = { Items: [], SelectedQuantity: 0, SelectedSubtotal: '0.00' }
    else if (endpoint === '/wishlist') result = { Items: [] }
    else if (endpoint === '/users/me/notifications') result = { Items: [], Total: 0 }
    else if (endpoint === '/users/me/notifications/unread-count') result = { Count: 0 }
    else if (endpoint === '/news') result = { Items: [{ NewsArticleId: 'n1', Title: 'Tin công nghệ', Slug: 'tin-cong-nghe' }], Total: 1 }
    else if (endpoint === '/news/tin-cong-nghe') result = { Title: 'Tin công nghệ', Content: 'Nội dung bài viết.' }
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
  ['/gio-hang', 'Giỏ hàng đang trống'], ['/yeu-thich', 'Chưa có sản phẩm yêu thích'],
  ['/thong-bao', 'Chưa có thông báo'], ['/tin-tuc', 'Tin tức công nghệ'],
  ['/tin-tuc/tin-cong-nghe', 'Tin công nghệ'],
])('home destination %s renders its page', async (url, heading) => {
  mockApi()
  renderAt(url, makeAuth({ role: 'Customer' }))
  expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Không tìm thấy trang' })).not.toBeInTheDocument()
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
