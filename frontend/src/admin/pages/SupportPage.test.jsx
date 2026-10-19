import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), claimSupportConversation: vi.fn(), sendSupportMessage: vi.fn(), closeSupportConversation: vi.fn(), markSupportRead: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData, getDashboardStock: async () => ({ Items: [], Total: 0 }), getRevenueSeries: async () => [] }))
vi.mock('../services/support.js', async (original) => ({ ...await original(), ...Object.fromEntries(Object.entries(api).filter(([key]) => key !== 'getAdminData')) }))
const permissions = ['admin.portal', 'chat:view', 'chat:create']
const initial = { ConversationId: 'c1', CustomerId: 'customer1', CustomerName: 'Nguyễn Văn An', CustomerEmail: 'an@example.com', Mode: 'Staff', Status: 'Open', AssignedStaffId: null, CreatedAt: '2026-10-14T08:00:00Z', ClosedAt: null }
const message = { MessageId: 'm1', ConversationId: 'c1', SenderType: 'Customer', MessageType: 'Text', Content: 'Tôi cần tư vấn về bảo hành.', SentAt: '2026-10-14T08:10:00Z' }
let conversations, messages, actorId
function open(path = '/admin/support', role = 'Admin', granted = permissions) {
  actorId = role + '-id'
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
const page = (items) => ({ Items: structuredClone(items), Total: items.length, Page: 1, PageSize: 100 })
beforeEach(() => {
  vi.resetAllMocks()
  conversations = [{ ...initial, LastMessage: message }]; messages = [{ ...message, IsRead: false }]; actorId = 'Admin-id'
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/conversations/unassigned') return page(conversations.filter((row) => row.Status === 'Open' && !row.AssignedStaffId))
    if (path === '/admin/conversations/assigned') return page(conversations.filter((row) => row.Status === (query?.status || 'Open') && row.AssignedStaffId === actorId))
    if (path === '/admin/conversations') return page(conversations.filter(row => !query?.status || row.Status === query.status))
    const row = conversations.find((row) => path === '/admin/conversations/' + row.ConversationId + '/summary')
    if (row) return structuredClone(row)
    const thread = conversations.find(row => path === '/admin/conversations/' + row.ConversationId + '/message-window')
    if (thread) {
      const all = messages.filter(m => m.ConversationId === thread.ConversationId).sort((a, b) => Date.parse(a.SentAt) - Date.parse(b.SentAt) || a.MessageId.localeCompare(b.MessageId))
      const items = query?.after_message_id ? all.slice(all.findIndex(m => m.MessageId === query.after_message_id) + 1) : query?.before_message_id ? all.slice(0, all.findIndex(m => m.MessageId === query.before_message_id)).slice(-50) : all.slice(-50)
      return { ...page(items), Total: all.length }
    }
    throw Object.assign(new Error('Không tìm thấy hội thoại'), { status: 404 })
  })
  api.claimSupportConversation.mockImplementation(async (_, id) => { const row = conversations.find((c) => c.ConversationId === id); row.AssignedStaffId = actorId; return structuredClone(row) })
  api.sendSupportMessage.mockImplementation(async (_, id, content) => { const reply = { ...message, MessageId: 'reply', ConversationId: id, SenderType: 'Staff', Content: content }; messages.push(reply); return reply })
  api.closeSupportConversation.mockImplementation(async (_, id) => { conversations.find((c) => c.ConversationId === id).Status = 'Closed' })
  api.markSupportRead.mockImplementation(async (_, id, ids) => { messages.forEach(message => { if (message.ConversationId === id && ids.includes(message.MessageId)) message.IsRead = true }); return { Updated: ids.length } })
})

test('waiting screen uses real counts and messages, omitting the unwanted instruction', async () => {
  open()
  const log = within(await screen.findByRole('log'))
  expect(log.getByText(message.Content)).toBeInTheDocument()
  expect(screen.getByText('Khách hàng • an@example.com')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Đang chờ 1' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: 'Đang hỗ trợ 0' })).toBeInTheDocument()
  expect(log.getByText('Cuộc trò chuyện đang chờ tiếp nhận')).toBeInTheDocument()
  expect(screen.queryByText(/Admin cần tiếp nhận/)).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(api.claimSupportConversation).not.toHaveBeenCalled()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/conversations/assigned', { status: 'Open', page: 1, page_size: 100 }, expect.any(AbortSignal))
})

test('empty inbox preserves workspace and zero counts without demonstration records', async () => {
  conversations = []
  open()
  await screen.findByText('Không có cuộc trò chuyện đang chờ.')
  expect(screen.getByRole('tab', { name: 'Đang chờ 0' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Đang hỗ trợ 0' })).toBeInTheDocument()
  expect(screen.queryByText(initial.CustomerName)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Tiếp nhận cuộc trò chuyện' })).not.toBeInTheDocument()
})

test.each([['Admin', 0], ['Staff', 2]])('the active badge and list belong to the signed-in %s account', async (role, expected) => {
  conversations = [
    { ...initial, ConversationId: 'c1', AssignedStaffId: 'Staff-id' },
    { ...initial, ConversationId: 'c2', CustomerName: 'Khách thứ hai', AssignedStaffId: 'Staff-id' },
    { ...initial, ConversationId: 'c3', CustomerName: 'Khách của nhân viên khác', AssignedStaffId: 'another-staff' },
    { ...initial, ConversationId: 'c4', CustomerName: 'Khách đã kết thúc', AssignedStaffId: 'Staff-id', Status: 'Closed' },
  ]
  open('/admin/support?tab=active', role)
  expect(await screen.findByRole('tab', { name: 'Đang hỗ trợ ' + expected })).toHaveAttribute('aria-selected', 'true')
  const list = within(screen.getByRole('complementary', { name: 'Danh sách cuộc trò chuyện' }))
  expect(list.queryAllByRole('button', { name: /Mở cuộc trò chuyện/ })).toHaveLength(expected)
  expect(list.queryByText('Khách của nhân viên khác')).not.toBeInTheDocument()
  expect(list.queryByText('Khách đã kết thúc')).not.toBeInTheDocument()
  if (role === 'Admin') expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  else expect(await screen.findByRole('textbox', { name: 'Tin nhắn trả lời' })).toBeInTheDocument()
})

test('staff claims then replies through existing endpoints; repeated clicks cannot duplicate writes', async () => {
  const router = open('/admin/support', 'Staff')
  let finish
  api.claimSupportConversation.mockImplementationOnce(() => new Promise((resolve) => { finish = () => { conversations[0].AssignedStaffId = actorId; resolve(conversations[0]) } }))
  const claim = await screen.findByRole('button', { name: 'Tiếp nhận cuộc trò chuyện' })
  fireEvent.click(claim); fireEvent.click(claim)
  expect(api.claimSupportConversation).toHaveBeenCalledTimes(1)
  await act(() => finish())
  const reply = await screen.findByRole('textbox', { name: 'Tin nhắn trả lời' })
  expect(router.state.location.search).toContain('tab=active')
  expect(router.state.location.search).toContain('conversation=c1')
  fireEvent.change(reply, { target: { value: '  Xin chào bạn  ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  await within(screen.getByRole('log')).findByText('Xin chào bạn')
  expect(api.sendSupportMessage).toHaveBeenCalledExactlyOnceWith('access-for-test', 'c1', 'Xin chào bạn')
  expect(reply).toHaveValue('')
})

test('competing claim shows server conflict and never opens a reply composer', async () => {
  open()
  api.claimSupportConversation.mockImplementationOnce(async () => { conversations[0].AssignedStaffId = 'other-staff'; throw Object.assign(new Error('Hội thoại đã được nhân viên khác nhận'), { status: 409 }) })
  fireEvent.click(await screen.findByRole('button', { name: 'Tiếp nhận cuộc trò chuyện' }))
  await screen.findByText('Hội thoại đã được nhân viên khác nhận')
  await screen.findByText('Cuộc trò chuyện đang do nhân viên khác phụ trách.')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Tiếp nhận cuộc trò chuyện' })).not.toBeInTheDocument()
})

test('Admin cannot reply to or close a conversation assigned to another staff member', async () => {
  conversations[0].AssignedStaffId = 'other-staff'
  open('/admin/support?conversation=c1')
  await screen.findByText('Cuộc trò chuyện đang do nhân viên khác phụ trách.')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Kết thúc hỗ trợ' })).not.toBeInTheDocument()
  expect(api.sendSupportMessage).not.toHaveBeenCalled()
})

test('view permission alone never exposes mutation controls', async () => {
  open('/admin/support', 'Staff', ['admin.portal', 'chat:view'])
  await screen.findByRole('log')
  expect(screen.queryByRole('button', { name: 'Tiếp nhận cuộc trò chuyện' })).not.toBeInTheDocument()
  expect(api.claimSupportConversation).not.toHaveBeenCalled()
})

test('failed send opens a modal over the current page and closing preserves the draft', async () => {
  conversations[0].AssignedStaffId = 'Admin-id'
  const router = open('/admin/support?tab=active')
  const reply = await screen.findByRole('textbox', { name: 'Tin nhắn trả lời' })
  fireEvent.change(reply, { target: { value: '<script>Không chạy mã</script>' } })
  api.sendSupportMessage.mockRejectedValueOnce(new Error('Mất kết nối khi gửi. Tải lại để kiểm tra tin nhắn.'))
  fireEvent.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  const error = within(await screen.findByRole('dialog', { name: 'Không gửi được tin nhắn' }))
  expect(error.getByText('Tin nhắn gửi đi thất bại. Vui lòng kiểm tra kết nối và thử lại.')).toBeInTheDocument()
  expect(reply).toHaveValue('<script>Không chạy mã</script>')
  expect(api.sendSupportMessage).toHaveBeenCalledTimes(1)
  expect(router.state.location.pathname).toBe('/admin/support')
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  fireEvent.click(error.getByRole('button', { name: 'Đóng' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(reply).toHaveValue('<script>Không chạy mã</script>')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Gửi tin nhắn' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  await within(screen.getByRole('log')).findByText('<script>Không chạy mã</script>')
  expect(screen.getByRole('log').querySelector('script')).toBeNull()
})

test('modal retry keeps the failed message and blocks repeated writes and dismissal while sending', async () => {
  conversations[0].AssignedStaffId = 'Admin-id'
  open('/admin/support?tab=active&conversation=c1')
  const reply = await screen.findByRole('textbox', { name: 'Tin nhắn trả lời' })
  fireEvent.change(reply, { target: { value: '  Nội dung gửi lại  ' } })
  api.sendSupportMessage.mockRejectedValueOnce(new Error('Mất kết nối'))
  fireEvent.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  const dialog = await screen.findByRole('dialog', { name: 'Không gửi được tin nhắn' })
  const ui = within(dialog), retry = ui.getByRole('button', { name: 'Thử lại' })
  await waitFor(() => expect(retry).toBeEnabled())
  let finish
  api.sendSupportMessage.mockImplementationOnce((_, id, content) => new Promise((resolve) => { finish = () => {
    const sent = { ...message, ConversationId: id, MessageId: 'retried', SenderType: 'Staff', Content: content }
    messages.push(sent); resolve(sent)
  } }))
  fireEvent.click(retry); fireEvent.click(retry)
  expect(api.sendSupportMessage).toHaveBeenCalledTimes(2)
  expect(api.sendSupportMessage.mock.calls[1]).toEqual(api.sendSupportMessage.mock.calls[0])
  expect(ui.getByRole('button', { name: 'Đóng' })).toBeDisabled()
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  fireEvent.click(dialog)
  expect(dialog).toBeInTheDocument()
  expect(reply).toHaveValue('  Nội dung gửi lại  ')
  await act(() => finish())
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  await within(screen.getByRole('log')).findByText('Nội dung gửi lại')
  expect(reply).toHaveValue('')
})

test('a second send failure retains one modal and a server-closed conversation cannot be retried', async () => {
  conversations[0].AssignedStaffId = 'Admin-id'
  open('/admin/support?tab=active&conversation=c1')
  const reply = await screen.findByRole('textbox', { name: 'Tin nhắn trả lời' })
  fireEvent.change(reply, { target: { value: 'Bản nháp còn nguyên' } })
  api.sendSupportMessage.mockRejectedValueOnce(new Error('Mất kết nối'))
  fireEvent.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }))
  const dialog = await screen.findByRole('dialog', { name: 'Không gửi được tin nhắn' }), ui = within(dialog)
  await waitFor(() => expect(ui.getByRole('button', { name: 'Thử lại' })).toBeEnabled())
  api.sendSupportMessage.mockImplementationOnce(async () => {
    conversations[0].Status = 'Closed'
    throw Object.assign(new Error('Hội thoại đã đóng, không gửi thêm tin nhắn'), { status: 400 })
  })
  fireEvent.click(ui.getByRole('button', { name: 'Thử lại' }))
  await ui.findByText('Hội thoại đã đóng, không gửi thêm tin nhắn')
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  await waitFor(() => expect(ui.getByRole('button', { name: 'Thử lại' })).toBeDisabled())
  expect(reply).toHaveValue('Bản nháp còn nguyên')
  expect(api.sendSupportMessage).toHaveBeenCalledTimes(2)
  fireEvent.click(ui.getByRole('button', { name: 'Đóng' }))
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})

test('closing needs confirmation and prevents additional replies after server closure', async () => {
  conversations[0].AssignedStaffId = 'Admin-id'
  open('/admin/support?tab=active')
  fireEvent.click(await screen.findByRole('button', { name: 'Kết thúc hỗ trợ' }))
  const modal = within(await screen.findByRole('dialog', { name: 'Kết thúc cuộc trò chuyện?' }))
  expect(api.closeSupportConversation).not.toHaveBeenCalled()
  fireEvent.click(modal.getByRole('button', { name: 'Hủy' }))
  expect(api.closeSupportConversation).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Kết thúc hỗ trợ' }))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Xác nhận kết thúc' }))
  await screen.findByText('Bạn chưa có cuộc trò chuyện đang hỗ trợ.')
  expect(api.closeSupportConversation).toHaveBeenCalledExactlyOnceWith('access-for-test', 'c1')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})

test('changing selection restores each conversation draft and browser history', async () => {
  conversations[0].AssignedStaffId = 'Admin-id'
  conversations.push({ ...initial, ConversationId: 'c2', CustomerName: 'Khách thứ hai', AssignedStaffId: 'Admin-id' })
  const router = open('/admin/support?tab=active&conversation=c1')
  fireEvent.change(await screen.findByRole('textbox', { name: 'Tin nhắn trả lời' }), { target: { value: 'Bản nháp thứ nhất' } })
  fireEvent.click(screen.getByRole('button', { name: 'Mở cuộc trò chuyện với Khách thứ hai' }))
  expect(await screen.findByRole('textbox', { name: 'Tin nhắn trả lời' })).toHaveValue('')
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Bản nháp thứ hai' } })
  await act(() => router.navigate(-1))
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Tin nhắn trả lời' })).toHaveValue('Bản nháp thứ nhất'))
})

test('list load errors do not fabricate zero counts and retry succeeds', async () => {
  const original = api.getAdminData.getMockImplementation()
  // Header notification also calls GET; fail specifically on the inbox.
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/conversations/unassigned' ? Promise.reject(new Error('Không tải được danh sách chat')) : original(...args))
  open()
  await screen.findByText('Không tải được danh sách chat')
  expect(screen.queryByRole('tab', { name: 'Đang chờ 0' })).not.toBeInTheDocument()
  api.getAdminData.mockImplementation(original)
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByRole('button', { name: 'Tiếp nhận cuộc trò chuyện' })
})

test('polling reloads incoming messages without clearing the reply draft', async () => {
  conversations[0].AssignedStaffId = 'Admin-id'
  await import('./SupportPage.jsx')
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    await act(async () => { open('/admin/support?tab=active&conversation=c1') })
    const reply = screen.getByRole('textbox', { name: 'Tin nhắn trả lời' })
    fireEvent.change(reply, { target: { value: 'Bản nháp' } })
    messages.push({ ...message, MessageId: 'm2', Content: 'Khách vừa gửi thêm' })
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(within(screen.getByRole('log')).getByText('Khách vừa gửi thêm')).toBeInTheDocument()
    expect(reply).toHaveValue('Bản nháp')
    expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/conversations/c1/message-window', { limit: 100, after_sent_at: message.SentAt, after_message_id: 'm1' }, expect.any(AbortSignal))
  } finally { vi.useRealTimers() }
})

test('manual refresh observes a customer closure and disables replies', async () => {
  conversations[0].AssignedStaffId = 'Admin-id'
  await import('./SupportPage.jsx')
  // Settle the initial read acknowledgement and the inbox refresh it triggers
  // before clicking a button whose enabled state depends on that refresh.
  await act(async () => { open('/admin/support?tab=active&conversation=c1') })
  const reply = screen.getByRole('textbox', { name: 'Tin nhắn trả lời' })
  fireEvent.change(reply, { target: { value: 'Chưa gửi' } })
  const refresh = screen.getByRole('button', { name: 'Làm mới' })
  expect(refresh).toBeEnabled()
  const original = api.getAdminData.getMockImplementation()
  let finishRefresh
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/conversations/c1/summary'
    ? new Promise(resolve => { finishRefresh = () => resolve(structuredClone(conversations[0])) }) : original(...args))
  conversations[0].Status = 'Closed'
  await act(async () => { fireEvent.click(refresh) })
  expect(finishRefresh).toBeTypeOf('function')
  expect(screen.getByRole('button', { name: 'Gửi tin nhắn' })).toBeDisabled()
  expect(reply).toHaveValue('Chưa gửi')
  await act(async () => { finishRefresh() })
  expect(screen.queryByRole('textbox', { name: 'Tin nhắn trả lời' })).not.toBeInTheDocument()
  expect(within(screen.getByRole('region', { name: 'Nội dung cuộc trò chuyện' })).getByText('Đã kết thúc')).toBeInTheDocument()
  expect(api.sendSupportMessage).not.toHaveBeenCalled()
  expect(api.closeSupportConversation).not.toHaveBeenCalled()
})

test('late detail response from an earlier selection cannot replace the selected chat', async () => {
  conversations.push({ ...initial, ConversationId: 'c2', CustomerName: 'Khách thứ hai' })
  const original = api.getAdminData.getMockImplementation()
  let finish
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/conversations/c1/summary' ? new Promise((resolve) => { finish = resolve }) : original(...args))
  open('/admin/support?conversation=c1')
  fireEvent.click(await screen.findByRole('button', { name: 'Mở cuộc trò chuyện với Khách thứ hai' }))
  await within(await screen.findByRole('region', { name: 'Nội dung cuộc trò chuyện' })).findByRole('heading', { name: 'Khách thứ hai' })
  await act(() => finish({ ...initial, Messages: [message] }))
  expect(within(screen.getByRole('region', { name: 'Nội dung cuộc trò chuyện' })).getByRole('heading', { name: 'Khách thứ hai' })).toBeInTheDocument()
  expect(within(screen.getByRole('log')).queryByText(message.Content)).not.toBeInTheDocument()
})

test('additional inbox pages keep totals and select the newly loaded conversation', async () => {
  const original = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation((token, path, query, signal) => path === '/admin/conversations/unassigned' ? Promise.resolve({ Items: query.page === 2 ? [{ ...initial, ConversationId: 'c101', CustomerName: 'Khách trang hai' }] : [initial], Total: 101, Page: query.page, PageSize: 100 }) : original(token, path, query, signal))
  const router = open()
  fireEvent.click(await screen.findByRole('button', { name: 'Sau', exact: true }))
  await screen.findByRole('button', { name: 'Mở cuộc trò chuyện với Khách trang hai' })
  expect(screen.getByText('Trang 2 / 2')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Đang chờ 101' })).toBeInTheDocument()
  expect(router.state.location.search).toContain('page=2')
  expect(screen.getByRole('button', { name: 'Mở cuộc trò chuyện với Khách trang hai' })).toHaveAttribute('aria-current', 'true')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/conversations/unassigned', { page: 2, page_size: 100 }, expect.any(AbortSignal))
})

test('refresh clamps a vanished last page after another staff member receives its last conversation', async () => {
  const original = api.getAdminData.getMockImplementation()
  let total = 101
  api.getAdminData.mockImplementation((token, path, query, signal) => path === '/admin/conversations/unassigned' ? Promise.resolve({ Items: query.page === 2 && total === 100 ? [] : [initial], Total: total, Page: query.page, PageSize: 100 }) : original(token, path, query, signal))
  const router = open('/admin/support?page=2&conversation=c1')
  await screen.findByText('Trang 2 / 2')
  total = 100
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await waitFor(() => expect(router.state.location.search).not.toContain('page='))
  await screen.findByRole('button', { name: 'Mở cuộc trò chuyện với Nguyễn Văn An' })
})

test.each([
  ['without a choice the first conversation is shown selected and the URL is left unchanged', '/admin/support', '', 'POP', 'Nguyễn Văn An'],
  ['a conversation already chosen in the URL is kept', '/admin/support?conversation=c2', '?conversation=c2', 'POP', 'Khách thứ hai'],
])('%s', async (_, path, search, historyAction, name) => {
  conversations = [{ ...initial, LastMessage: message }, { ...initial, ConversationId: 'c2', CustomerName: 'Khách thứ hai' }]
  const router = open(path)
  await within(await screen.findByRole('region', { name: 'Nội dung cuộc trò chuyện' })).findByRole('heading', { name })
  await waitFor(() => expect(router.state.location.search).toBe(search))
  expect(router.state.historyAction).toBe(historyAction)
  expect(screen.getByRole('button', { name: 'Mở cuộc trò chuyện với ' + name })).toHaveAttribute('aria-current', 'true')
})

// Clicks what `find` returns in the microtask after React commits it, before React runs that
// render's passive effects (they run in a later task): a click a user on a slow device can make.
// Resolves with the URL the router had at the click.
function clickBeforeEffects(router, find) {
  return new Promise((resolve) => {
    const observer = new MutationObserver(() => {
      const target = find()
      if (!target || target.disabled) return
      observer.disconnect()
      const search = router.state.location.search
      fireEvent.click(target)
      resolve(search)
    })
    observer.observe(document.body, { childList: true, subtree: true, attributes: true })
  })
}

test('pressing Sau right after the first page renders stays on page 2', async () => {
  const original = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation((token, path, query, signal) => path === '/admin/conversations/unassigned' ? Promise.resolve({ Items: query.page === 2 ? [{ ...initial, ConversationId: 'c101', CustomerName: 'Khách trang hai' }] : [initial], Total: 101, Page: query.page, PageSize: 100 }) : original(token, path, query, signal))
  const router = open()
  // Page 1 is on screen and its effects have not run yet.
  expect(await clickBeforeEffects(router, () => screen.queryByRole('button', { name: 'Sau', exact: true }))).toBe('')
  await screen.findByRole('button', { name: 'Mở cuộc trò chuyện với Khách trang hai' })
  expect(screen.getByText('Trang 2 / 2')).toBeInTheDocument()
  await waitFor(() => expect(router.state.location.search).toBe('?page=2'))
  expect(screen.getByRole('button', { name: 'Mở cuộc trò chuyện với Khách trang hai' })).toHaveAttribute('aria-current', 'true')
  expect(screen.queryByRole('button', { name: 'Mở cuộc trò chuyện với Nguyễn Văn An' })).not.toBeInTheDocument()
})

test('switching tab while a page past the last one is being clamped keeps the chosen tab', async () => {
  const original = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation((token, path, query, signal) => path === '/admin/conversations/unassigned' ? Promise.resolve({ Items: query.page === 3 ? [] : [initial], Total: 150, Page: query.page, PageSize: 100 }) : original(token, path, query, signal))
  const router = open('/admin/support?page=3')
  // Page 3 of 2 is on screen and has not been clamped yet.
  expect(await clickBeforeEffects(router, () => screen.queryByText('Trang 3 / 2') && screen.getByRole('tab', { name: /^Đang hỗ trợ/ }))).toBe('?page=3')
  expect(await screen.findByText('Bạn chưa có cuộc trò chuyện đang hỗ trợ.')).toBeInTheDocument()
  await waitFor(() => expect(router.state.location.search).toBe('?tab=active'))
  expect(screen.getByRole('tab', { name: /^Đang hỗ trợ/ })).toHaveAttribute('aria-selected', 'true')
})

test('transcript sorts by server timestamp and message ID instead of database relationship order', async () => {
  messages = [{ ...message, MessageId: 'm3', Content: 'Cuối', SentAt: '2026-10-14T08:11:00Z' }, { ...message, MessageId: 'm2', Content: 'Thứ hai' }, { ...message, Content: 'Đầu tiên' }]
  open()
  const log = await screen.findByRole('log')
  expect([...log.querySelectorAll('article p:first-child')].map((p) => p.textContent)).toEqual(['Đầu tiên', 'Thứ hai', 'Cuối'])
})

test.each(['Admin', 'Staff'])('%s opens closed history using the permitted scope without reply controls', async role => {
  conversations[0].AssignedStaffId = role + '-id'; conversations[0].Status = 'Closed'
  open('/admin/support?tab=closed', role)
  const log = await screen.findByRole('log')
  expect(within(log).getByText(message.Content)).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Kết thúc hỗ trợ' })).not.toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', role === 'Admin' ? '/admin/conversations' : '/admin/conversations/assigned', { status: 'Closed', page: 1, page_size: 100 }, expect.any(AbortSignal))
})

test('Admin all-conversations view does not grant takeover or mark another operator’s messages read', async () => {
  conversations[0].AssignedStaffId = 'another-staff'
  open('/admin/support?tab=all')
  await screen.findByText('Cuộc trò chuyện đang do nhân viên khác phụ trách.')
  expect(screen.getByRole('tab', { name: 'Tất cả hội thoại 1' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(api.markSupportRead).not.toHaveBeenCalled()
})

test('Staff cannot select the Admin all-conversations scope through the URL', async () => {
  open('/admin/support?tab=all', 'Staff')
  await screen.findByRole('log')
  expect(screen.queryByRole('tab', { name: /Tất cả hội thoại/ })).not.toBeInTheDocument()
  expect(api.getAdminData.mock.calls.some(([, path]) => path === '/admin/conversations')).toBe(false)
})

test('Admin can observe existing AI conversations without receiving staff claim or reply controls', async () => {
  conversations[0].Mode = 'AI'
  open('/admin/support?tab=all')
  await screen.findByText('Hội thoại với AI chỉ được xem tại đây.')
  expect(screen.queryByRole('button', { name: 'Tiếp nhận cuộc trò chuyện' })).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(api.markSupportRead).not.toHaveBeenCalled()
})

test('only the opened assigned thread marks incoming customer messages read', async () => {
  conversations[0].AssignedStaffId = 'Staff-id'
  messages.push({ ...message, MessageId: 'staff-reply', SenderType: 'Staff' })
  open('/admin/support?tab=active', 'Staff')
  await waitFor(() => expect(api.markSupportRead).toHaveBeenCalledExactlyOnceWith('access-for-test', 'c1', ['m1']))
  expect(await within(screen.getByRole('log')).findByText(/Đã đọc/)).toBeInTheDocument()
})

test('long threads fetch the latest window then load older messages without requesting the full transcript', async () => {
  messages = Array.from({ length: 120 }, (_, i) => ({ ...message, MessageId: 'm' + String(i).padStart(3, '0'), Content: 'Nội dung ' + i }))
  open('/admin/support?conversation=c1')
  await within(await screen.findByRole('log')).findByText('Nội dung 119', { exact: true })
  expect(screen.queryByText('Nội dung 0', { exact: true })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Xem tin nhắn cũ hơn' }))
  await within(screen.getByRole('log')).findByText('Nội dung 20', { exact: true })
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/conversations/c1/message-window', { limit: 50, before_sent_at: message.SentAt, before_message_id: 'm070' }, expect.any(AbortSignal))
  expect(api.getAdminData.mock.calls.some(([, path]) => path === '/admin/conversations/c1')).toBe(false)
})

test('on compact screens the inbox opens first and reads start only after selecting a conversation', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }))
  try {
    conversations[0].AssignedStaffId = 'Staff-id'
    open('/admin/support?tab=active', 'Staff')
    const row = await screen.findByRole('button', { name: 'Mở cuộc trò chuyện với Nguyễn Văn An' })
    expect(api.markSupportRead).not.toHaveBeenCalled()
    expect(screen.queryByRole('log')).not.toBeInTheDocument()
    fireEvent.click(row)
    await screen.findByRole('textbox', { name: 'Tin nhắn trả lời' })
    await waitFor(() => expect(api.markSupportRead).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Quay lại danh sách hội thoại' }))
    expect(document.querySelector('#support-workspace')).toHaveAttribute('data-mobile-view', 'list')
  } finally { vi.unstubAllGlobals() }
})
