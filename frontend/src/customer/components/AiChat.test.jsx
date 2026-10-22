import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import AiChat from './AiChat.jsx'
import ChatDraftProvider from './ChatDraftProvider.jsx'
import { turnStorageKey } from './ai-chat-state.js'

const conversation = { ConversationId: 'ai1', Mode: 'AI', Status: 'Open', CreatedAt: '2026-10-22T08:00:00Z', Messages: [] }
const message = (id, type, content, metadata = null) => ({ MessageId: id, ConversationId: 'ai1', SenderType: type,
  MessageType: 'Text', Content: content, Metadata: metadata, SentAt: '2026-10-22T08:01:00Z' })
function result(body, status = 'Completed') {
  return { ClientRequestId: body.ClientRequestId, Status: status,
    CustomerMessage: message('question', 'Customer', body.Content, { ClientRequestId: body.ClientRequestId, AiProcessingStatus: status }),
    AiMessages: status === 'Completed' ? [message('answer', 'AI', '<script>alert(1)</script> Kết quả từ catalog')] : [] }
}

function mockApi({ open = conversation, history = [], post, status, cancel, closeFailure = false } = {}) {
  const calls = []
  let active = open ? { ...open } : null
  let detail = { ...conversation, ...open }
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost')
    const path = url.pathname.replace('/api', '')
    const method = options.method ?? 'GET'
    const body = options.body ? JSON.parse(options.body) : null
    calls.push({ path, method, body, token: options.headers.Authorization, query: Object.fromEntries(url.searchParams) })
    let data
    if (path.endsWith('/ai-messages') && method === 'POST') {
      data = post ? await post(body, options) : result(body)
      if (data instanceof Response) return data
      detail.Messages = [data.CustomerMessage, ...data.AiMessages]
    } else if (path.endsWith('/cancel') && method === 'POST') {
      data = cancel ? await cancel(body, options, path) : result({
        ClientRequestId: path.split('/').at(-2), Content: body.Content,
      }, 'Cancelled')
      if (data instanceof Response) return data
      detail.Messages = [data.CustomerMessage, ...data.AiMessages]
    } else if (path.includes('/ai-messages/')) {
      data = status ? await status(path, options) : new Response(JSON.stringify({ code: 'ai_request_not_found', detail: 'Không tìm thấy yêu cầu AI' }), { status: 404 })
      if (data instanceof Response) return data
    } else if (path.endsWith('/close')) {
      if (closeFailure) return new Response(JSON.stringify({ detail: 'Chưa đóng được hội thoại' }), { status: 503 })
      active = null; detail = { ...detail, Status: 'Closed' }; data = detail
    } else if (path === '/conversations' && method === 'POST') {
      // Like the server: an open conversation of the other mode blocks only once it has messages.
      if (active && active.Mode !== body.Mode && active.Messages?.length) {
        return new Response(JSON.stringify({ code: 'open_conversation_exists', detail: 'Đang có hội thoại mở ở chế độ khác' }), { status: 400 })
      }
      active = { ...conversation, Mode: body.Mode }; detail = { ...active }; data = active
    } else if (path === '/conversations') data = url.searchParams.has('status')
      ? { Items: active ? [active] : [], Total: active ? 1 : 0 }
      : { Items: [...history, ...(active ? [active] : [])], Total: history.length + (active ? 1 : 0) }
    else if (path.startsWith('/conversations/')) data = history.find((item) => path.endsWith(item.ConversationId)) ?? detail
    else throw new Error(`Unexpected ${path}`)
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
  return calls
}
function renderChat({ auth = makeAuth({ role: 'Customer' }), onDismiss = vi.fn() } = {}) {
  const app = <AuthContext.Provider value={auth}><MemoryRouter initialEntries={['/san-pham/laptop']}><ChatDraftProvider>
    <AiChat titleId="ai-title" onDismiss={onDismiss} />
  </ChatDraftProvider></MemoryRouter></AuthContext.Provider>
  return { ...render(app), app, onDismiss }
}
async function ask(content = 'Laptop dưới 20 triệu') {
  const input = await screen.findByRole('textbox', { name: 'Câu hỏi cho AI' })
  fireEvent.change(input, { target: { value: content } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi câu hỏi AI' }))
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); sessionStorage.clear() })

test('guests see a login link preserving the current product and make no chat requests', () => {
  const calls = mockApi()
  renderChat({ auth: makeAuth() })
  expect(screen.getByRole('link', { name: 'Đăng nhập' })).toHaveAttribute('href', '/dang-nhap?next=%2Fsan-pham%2Flaptop')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(calls).toHaveLength(0)
})

test('reuses an AI conversation, sends one authenticated UUID turn and renders safe text and backend cards', async () => {
  const calls = mockApi({ post: async (body) => {
    const response = result(body)
    response.AiMessages.push(...[3, 1, 2, 4].map((rank) => ({ ...message(`product${rank}`, 'AI', ''), MessageType: 'Product', Metadata: {
      AiAnswerMessageId: 'answer', ProductName: `Laptop ${rank}`, Slug: `laptop-${rank}`, VariantName: '16GB / 512GB',
      Price: '18000000', OriginalPrice: '20000000', InStock: true, Rank: rank, ImageUrl: 'javascript:alert(1)',
    } })))
    return response
  } })
  renderChat()
  await ask('  Laptop dưới 20 triệu  ')
  expect(await screen.findByText('<script>alert(1)</script> Kết quả từ catalog')).toBeInTheDocument()
  const posts = calls.filter((call) => call.path.endsWith('/ai-messages') && call.method === 'POST')
  expect(posts).toHaveLength(1)
  expect(posts[0]).toMatchObject({ token: 'Bearer access-for-test', body: { Content: 'Laptop dưới 20 triệu', MessageType: 'Text' } })
  expect(posts[0].body.ClientRequestId).toMatch(/^[\da-f-]{36}$/)
  expect(calls.filter((call) => call.path === '/conversations' && call.method === 'POST')).toHaveLength(0)
  const links = within(screen.getByRole('log')).getAllByRole('link')
  expect(links.map((link) => link.getAttribute('href'))).toEqual(['/san-pham/laptop-1', '/san-pham/laptop-2', '/san-pham/laptop-3'])
  expect(links[0]).toHaveTextContent('18.000.000')
  expect(document.querySelector('script')).toBeNull()
  expect(screen.getByRole('textbox')).toHaveValue('')
})

test('creating AI uses Mode AI; a staff session with messages is closed only after the explicit switch action', async () => {
  const calls = mockApi({ open: { ...conversation, Mode: 'Staff', Messages: [message('staffmsg', 'Customer', 'Cần hỗ trợ đơn hàng')] } })
  renderChat()
  expect(await screen.findByRole('heading', { name: 'Bạn đang có phiên tư vấn khác' })).toBeInTheDocument()
  expect(calls.some((call) => call.path.endsWith('/close'))).toBe(false)
  await userEvent.setup().click(screen.getByRole('button', { name: 'Kết thúc phiên hiện tại và mở AI' }))
  await screen.findByRole('textbox')
  expect(calls.filter((call) => call.method === 'POST').map((call) => [call.path, call.body])).toEqual([
    ['/conversations', { Mode: 'AI' }], ['/conversations/ai1/close', null], ['/conversations', { Mode: 'AI' }],
  ])
})

test('an unused staff session does not block AI: the panel opens without a switch prompt', async () => {
  const calls = mockApi({ open: { ...conversation, Mode: 'Staff' } })
  renderChat()
  await screen.findByRole('textbox')
  expect(screen.queryByRole('heading', { name: 'Bạn đang có phiên tư vấn khác' })).not.toBeInTheDocument()
  expect(calls.filter((call) => call.method === 'POST').map((call) => [call.path, call.body])).toEqual([
    ['/conversations', { Mode: 'AI' }],
  ])
})

test('first opening creates AI and IME, shift-enter and blank input never submit a turn', async () => {
  const calls = mockApi({ open: null })
  renderChat()
  const input = await screen.findByRole('textbox')
  expect(calls.find((call) => call.method === 'POST').body).toEqual({ Mode: 'AI' })
  expect(input).toHaveAttribute('maxlength', '1000')
  fireEvent.change(input, { target: { value: '  ' } }); fireEvent.keyDown(input, { key: 'Enter' })
  fireEvent.change(input, { target: { value: 'Laptop' } })
  fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
  expect(calls.some((call) => call.path.endsWith('/ai-messages'))).toBe(false)
  fireEvent.keyDown(input, { key: 'Enter' })
  await screen.findByText(/Kết quả từ catalog/)
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(1)
})

test('Pending blocks duplicate submissions and polls status without resending', async () => {
  let body
  const calls = mockApi({ post: async (data) => { body = data; return result(data, 'Pending') }, status: async () => result(body) })
  renderChat(); await ask()
  expect(screen.getByRole('textbox')).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Dừng trả lời AI' })).toBeEnabled()
  fireEvent.submit(screen.getByRole('textbox').closest('form'))
  expect(await screen.findByText(/Kết quả từ catalog/, {}, { timeout: 6000 })).toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(1)
  expect(screen.getAllByText('Laptop dưới 20 triệu', { exact: true })).toHaveLength(1)
  expect(sessionStorage.getItem(turnStorageKey('Customer-id', 'ai1'))).toBeNull()
})

test('retry checks status first and reuses exactly the original UUID and content after a network failure', async () => {
  let count = 0
  const calls = mockApi({ post: async (body) => { if (!count++) throw new TypeError('offline'); return result(body) } })
  renderChat(); await ask()
  const retry = await screen.findByRole('button', { name: 'Kiểm tra và thử lại' })
  await userEvent.setup().click(retry)
  await screen.findByText(/Kết quả từ catalog/)
  const posts = calls.filter((call) => call.path.endsWith('/ai-messages'))
  expect(posts).toHaveLength(2)
  expect(posts[1].body).toEqual(posts[0].body)
  expect(calls.slice(calls.indexOf(posts[0]) + 1, calls.indexOf(posts[1])).some((call) => call.path.endsWith(posts[0].body.ClientRequestId))).toBe(true)
})

test('remount resumes a stored Pending request and never starts another POST', async () => {
  const body = { ClientRequestId: crypto.randomUUID(), Content: 'Câu hỏi đang xử lý' }
  sessionStorage.setItem(turnStorageKey('Customer-id', 'ai1'), JSON.stringify({ id: body.ClientRequestId, content: body.Content }))
  const calls = mockApi({ status: async () => result(body) })
  renderChat()
  await screen.findByText(/Kết quả từ catalog/)
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(0)
  expect(calls.some((call) => call.path.endsWith(body.ClientRequestId))).toBe(true)
})

test('request markers belong to their customer and are not displayed for a different signed-in user', async () => {
  sessionStorage.setItem(turnStorageKey('someone-else', 'ai1'), JSON.stringify({ id: crypto.randomUUID(), content: 'Bí mật của khách khác' }))
  const calls = mockApi()
  renderChat()
  await screen.findByRole('textbox')
  expect(screen.queryByText('Bí mật của khách khác')).not.toBeInTheDocument()
  expect(calls.some((call) => call.path.includes('/ai-messages'))).toBe(false)
})

test('closing during an in-flight POST preserves its UUID and reopening recovers the server completion', async () => {
  let body
  const calls = mockApi({ post: (data, options) => { body = data; return new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Closed', 'AbortError')))) },
    status: async () => result(body) })
  const view = renderChat()
  await ask()
  const stored = JSON.parse(sessionStorage.getItem(turnStorageKey('Customer-id', 'ai1')))
  expect(stored.id).toBe(body.ClientRequestId)
  view.unmount()
  renderChat()
  await screen.findByText(/Kết quả từ catalog/)
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(1)
  expect(calls.some((call) => call.path.endsWith(stored.id))).toBe(true)
})

test.each(['Completed', 'Cancelled'])('a %s turn in history clears a stale local marker without another status call', async (status) => {
  const body = { ClientRequestId: crypto.randomUUID(), Content: 'Câu hỏi đã trả lời' }
  sessionStorage.setItem(turnStorageKey('Customer-id', 'ai1'), JSON.stringify({ id: body.ClientRequestId, content: body.Content }))
  const response = result(body, status)
  const calls = mockApi({ open: { ...conversation, Messages: [response.CustomerMessage, ...response.AiMessages] } })
  renderChat()
  expect(await screen.findByRole('textbox')).toBeEnabled()
  expect(sessionStorage.getItem(turnStorageKey('Customer-id', 'ai1'))).toBeNull()
  expect(calls.some((call) => call.path.includes('/ai-messages'))).toBe(false)
})

test('sending clears the composer immediately and shows a square until the response completes', async () => {
  let finish
  const gate = new Promise((resolve) => { finish = resolve })
  const calls = mockApi({ post: async (body) => { await gate; return result(body) } })
  renderChat()
  await ask('  Laptop dưới 20 triệu  ')
  expect(screen.getByRole('textbox')).toHaveValue('')
  expect(screen.getByRole('textbox')).toBeDisabled()
  const stop = screen.getByRole('button', { name: 'Dừng trả lời AI' })
  expect(stop).toBeEnabled()
  expect(stop.querySelector('svg rect')).not.toBeNull()
  expect(screen.queryByRole('button', { name: 'Gửi câu hỏi AI' })).not.toBeInTheDocument()
  expect(within(screen.getByRole('log')).getByText('Laptop dưới 20 triệu')).toBeInTheDocument()
  await act(async () => { finish() })
  expect(await screen.findByRole('button', { name: 'Gửi câu hỏi AI' })).toBeDisabled()
  expect(screen.getByRole('textbox')).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Dừng trả lời AI' })).not.toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(1)
})

test('stopping aborts the browser request, persists cancellation and ignores a late answer after a new turn', async () => {
  let finishOld, signal, count = 0
  const calls = mockApi({ post: (body, options) => {
    if (count++) return result(body)
    signal = options.signal
    return new Promise((resolve) => { finishOld = () => {
      const late = result(body); late.AiMessages[0].Content = 'Phản hồi cũ sau khi dừng'
      resolve(late)
    } })
  } })
  renderChat()
  await ask('Câu hỏi cần dừng')
  fireEvent.click(screen.getByRole('button', { name: 'Dừng trả lời AI' }))
  expect(signal.aborted).toBe(true)
  expect(await screen.findByText('Đã dừng trả lời.')).toBeInTheDocument()
  expect(screen.getByRole('textbox')).toBeEnabled()
  expect(sessionStorage.getItem(turnStorageKey('Customer-id', 'ai1'))).toBeNull()
  const first = calls.find((call) => call.path.endsWith('/ai-messages'))
  expect(calls.find((call) => call.path.endsWith('/cancel'))).toMatchObject({
    path: `/conversations/ai1/ai-messages/${first.body.ClientRequestId}/cancel`, body: { Content: 'Câu hỏi cần dừng' },
  })
  await ask('Câu hỏi mới')
  expect(await screen.findByText(/Kết quả từ catalog/)).toBeInTheDocument()
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Bản nháp mới' } })
  await act(async () => { finishOld() })
  expect(screen.queryByText('Phản hồi cũ sau khi dừng')).not.toBeInTheDocument()
  expect(screen.getByRole('textbox')).toHaveValue('Bản nháp mới')
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(2)
})

test('stopping a recovered Pending turn stops polling and ignores a late status response', async () => {
  const body = { ClientRequestId: crypto.randomUUID(), Content: 'Lượt đang chờ' }
  let finishStatus, signal
  const calls = mockApi({ open: { ...conversation, Messages: [result(body, 'Pending').CustomerMessage] },
    status: (_path, options) => {
      signal = options.signal
      return new Promise((resolve) => { finishStatus = () => resolve(result(body)) })
    } })
  renderChat()
  await screen.findByRole('textbox')
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
  expect(signal).toBeDefined()
  fireEvent.click(screen.getByRole('button', { name: 'Dừng trả lời AI' }))
  expect(await screen.findByText('Đã dừng trả lời.')).toBeInTheDocument()
  expect(signal.aborted).toBe(true)
  const count = calls.length
  await act(async () => { finishStatus() })
  expect(screen.queryByText(/Kết quả từ catalog/)).not.toBeInTheDocument()
  expect(calls).toHaveLength(count)
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(0)
})

test('an unconfirmed stop can be retried without resending the question', async () => {
  let attempts = 0
  const calls = mockApi({ post: (_body, options) => new Promise((_, reject) =>
    options.signal.addEventListener('abort', () => reject(new DOMException('Stopped', 'AbortError')))),
    cancel: (body, _options, path) => {
      if (!attempts++) throw new TypeError('offline')
      return result({ ClientRequestId: path.split('/').at(-2), Content: body.Content }, 'Cancelled')
    } })
  renderChat(); await ask()
  fireEvent.click(screen.getByRole('button', { name: 'Dừng trả lời AI' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Chưa xác nhận được việc dừng')
  expect(screen.getByRole('textbox')).toBeDisabled()
  expect(JSON.parse(sessionStorage.getItem(turnStorageKey('Customer-id', 'ai1'))).cancelRequested).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Thử dừng lại' }))
  expect(await screen.findByText('Đã dừng trả lời.')).toBeInTheDocument()
  expect(screen.getByRole('textbox')).toBeEnabled()
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(1)
  expect(calls.filter((call) => call.path.endsWith('/cancel'))).toHaveLength(2)
})

test('closing during cancellation resumes the stop on reopening without sending another question', async () => {
  let body, attempts = 0
  const calls = mockApi({ post: (data) => { body = data; return result(data, 'Pending') },
    status: () => result(body, 'Pending'),
    cancel: (data, options, path) => {
      if (!attempts++) return new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Closed', 'AbortError'))))
      return result({ ClientRequestId: path.split('/').at(-2), Content: data.Content }, 'Cancelled')
    } })
  const view = renderChat(); await ask()
  fireEvent.click(screen.getByRole('button', { name: 'Dừng trả lời AI' }))
  expect(JSON.parse(sessionStorage.getItem(turnStorageKey('Customer-id', 'ai1'))).cancelRequested).toBe(true)
  view.unmount(); renderChat()
  expect(await screen.findByText('Đã dừng trả lời.')).toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(1)
  const stops = calls.filter((call) => call.path.endsWith('/cancel'))
  expect(stops).toHaveLength(2)
  expect(stops[1].path).toBe(stops[0].path)
})

test('if completion wins the stop race the saved answer is displayed and the arrow returns', async () => {
  mockApi({ post: (_body, options) => new Promise((_, reject) =>
    options.signal.addEventListener('abort', () => reject(new DOMException('Stopped', 'AbortError')))),
    cancel: (body, _options, path) => result({ ClientRequestId: path.split('/').at(-2), Content: body.Content }) })
  renderChat(); await ask()
  fireEvent.click(screen.getByRole('button', { name: 'Dừng trả lời AI' }))
  expect(await screen.findByText(/Kết quả từ catalog/)).toBeInTheDocument()
  expect(screen.getByRole('textbox')).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Gửi câu hỏi AI' })).toBeInTheDocument()
  expect(sessionStorage.getItem(turnStorageKey('Customer-id', 'ai1'))).toBeNull()
})

test('history includes only AI, closed threads are read-only, and new conversations stay in AI mode', async () => {
  const old = { ...conversation, ConversationId: 'old', Title: 'Chọn laptop học tập', Status: 'Closed', Messages: [message('oldmsg', 'AI', 'Tư vấn trước đây')] }
  const calls = mockApi({ history: [old, { ...old, ConversationId: 'staffold', Mode: 'Staff' }] })
  renderChat()
  const user = userEvent.setup()
  await screen.findByRole('textbox')
  await user.click(screen.getByRole('button', { name: 'Lịch sử AI' }))
  const history = await screen.findByRole('region', { name: 'Lịch sử chat AI' })
  expect(await within(history).findByText('Chọn laptop học tập')).toBeInTheDocument()
  expect(calls.some((call) => call.path === '/conversations' && call.query.mode === 'AI')).toBe(true)
  await user.click(await within(history).findByRole('button', { name: /Đã kết thúc/ }))
  await screen.findByText('Tư vấn trước đây')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Bắt đầu cuộc trò chuyện mới' }))
  await screen.findByRole('textbox')
  expect(calls.filter((call) => call.method === 'POST').map((call) => [call.path, call.body])).toEqual([
    ['/conversations/ai1/close', null], ['/conversations', { Mode: 'AI' }],
  ])
})

test('failure to close the old conversation prevents creating a new conversation', async () => {
  const calls = mockApi({ closeFailure: true })
  renderChat()
  await screen.findByRole('textbox')
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Lịch sử AI' }))
  await user.click(screen.getByRole('button', { name: 'Cuộc trò chuyện mới' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Chưa đóng được hội thoại')
  expect(calls.some((call) => call.path === '/conversations' && call.method === 'POST')).toBe(false)
})

test('the AI panel never offers or automatically creates staff support', async () => {
  const calls = mockApi({ open: { ...conversation, Mode: 'Staff', Messages: [message('staffmsg', 'Customer', 'Cần hỗ trợ đơn hàng')] } })
  renderChat()
  await screen.findByRole('heading', { name: 'Bạn đang có phiên tư vấn khác' })
  expect(screen.queryByRole('button', { name: 'Chat với nhân viên' })).not.toBeInTheDocument()
  expect(calls.filter((call) => call.method === 'POST').map((call) => [call.path, call.body])).toEqual([
    ['/conversations', { Mode: 'AI' }],
  ])
})

test('customers only ask questions: no personalization or save-preference controls and no profile requests', async () => {
  const question = message('q1', 'Customer', 'Laptop học lập trình dưới 20 triệu', { ClientRequestId: 'r1', AiProcessingStatus: 'Completed' })
  const calls = mockApi({ open: { ...conversation, Messages: [question] } })
  renderChat()
  await screen.findByText('Laptop học lập trình dưới 20 triệu')
  expect(screen.queryByRole('button', { name: /Cá nhân hóa|sở thích|nhu cầu/i })).not.toBeInTheDocument()
  expect(calls.some((call) => call.path.startsWith('/users/'))).toBe(false)
  // Advice comes from the catalog and the customer's request; wishlist and orders are not used.
  expect(screen.getByText(/gợi ý dựa trên sản phẩm đang bán tại VieTech và nhu cầu bạn nêu/)).toBeInTheDocument()
  expect(screen.queryByText(/đã yêu thích hoặc đã mua/)).not.toBeInTheDocument()
})

test('suggestion cards fill the composer without sending and history keeps the draft; Escape closes only history', async () => {
  const calls = mockApi()
  const { onDismiss } = renderChat()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /Chọn laptop/ }))
  const content = screen.getByRole('textbox').value
  expect(content).toContain('dưới 20 triệu')
  expect(screen.getByRole('textbox')).toHaveFocus()
  expect(calls.some((call) => call.path.endsWith('/ai-messages'))).toBe(false)
  await user.click(screen.getByRole('button', { name: 'Lịch sử AI' }))
  const history = await screen.findByRole('region', { name: 'Lịch sử chat AI' })
  expect(history).toHaveFocus()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('region', { name: 'Lịch sử chat AI' })).not.toBeInTheDocument()
  expect(screen.getByRole('textbox')).toHaveValue(content)
  expect(screen.getByRole('button', { name: 'Lịch sử AI' })).toHaveFocus()
  expect(onDismiss).not.toHaveBeenCalled()
})

test('viewing history during a send keeps the request alive and its completed response', async () => {
  let finish, signal
  const gate = new Promise((resolve) => { finish = resolve })
  const calls = mockApi({ post: async (body, options) => { signal = options.signal; await gate; return result(body) } })
  renderChat()
  await ask()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Lịch sử AI' }))
  expect(signal.aborted).toBe(false)
  await act(async () => { finish() })
  await userEvent.setup().click(screen.getByRole('button', { name: 'Đóng lịch sử' }))
  expect(await screen.findByText(/Kết quả từ catalog/)).toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(1)
})

test('a POST timeout recovers the completed response without generating a second request', async () => {
  let body
  const calls = mockApi({ post: (data, options) => { body = data; return new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Timeout', 'AbortError')))) }, status: async () => result(body) })
  renderChat()
  await screen.findByRole('textbox')
  vi.useFakeTimers()
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Laptop dưới 20 triệu' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi câu hỏi AI' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(77010) })
  await act(async () => { await vi.advanceTimersByTimeAsync(10) })
  expect(screen.getByText(/Kết quả từ catalog/)).toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(1)
})

test('repeated Pending polls continue until completion with no extra POST', async () => {
  const body = { ClientRequestId: crypto.randomUUID(), Content: 'Câu hỏi từ phiên trước' }
  let polls = 0
  const calls = mockApi({ open: { ...conversation, Messages: [result(body, 'Pending').CustomerMessage] },
    status: async () => result(body, ++polls < 3 ? 'Pending' : 'Completed') })
  renderChat()
  await screen.findByRole('textbox')
  vi.useFakeTimers()
  // Trigger status recovery manually if the initial zero-delay timer preceded fake timers.
  for (let index = 0; index < 4; index++) {
    await act(async () => { await vi.advanceTimersByTimeAsync(2100) })
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  }
  expect(screen.getByText(/Kết quả từ catalog/)).toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/ai-messages'))).toHaveLength(0)
  expect(polls).toBe(3)
})

test('Retry-After prevents early retries and terminal retry caps allow abandoning the failed question', async () => {
  let body, posts = 0
  mockApi({ post: async (data) => {
    body = data
    return new Response(JSON.stringify({ code: posts++ ? 'ai_retry_limit' : 'ai_quota_exceeded', detail: 'AI tạm hết lượt, vui lòng chờ.' }),
      { status: posts === 1 ? 503 : 409, headers: posts === 1 ? { 'Retry-After': '5' } : {} })
  }, status: async () => result(body, 'Failed') })
  renderChat()
  await screen.findByRole('textbox')
  vi.useFakeTimers()
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Laptop dưới 20 triệu' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi câu hỏi AI' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(screen.getByRole('button', { name: /Thử lại sau/ })).toBeDisabled()
  await act(async () => { await vi.advanceTimersByTimeAsync(5100) })
  fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra và thử lại' }))
  await act(async () => {})
  expect(posts).toBe(2)
  expect(screen.queryByRole('button', { name: 'Kiểm tra và thử lại' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua câu hỏi' }))
  expect(screen.getByRole('textbox')).toBeEnabled()
})
