import { afterEach, expect, test, vi } from 'vitest'
import { claimSupportConversation, closeSupportConversation, getSupportConversation, getSupportInbox, getSupportMessages, getSupportPage, markSupportRead, sendSupportMessage } from './support.js'

afterEach(() => vi.unstubAllGlobals())
test('inbox reads the waiting queue and only the signed-in operator’s open assignments', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ Items: [], Total: 0, Page: 1, PageSize: 100 })))
  vi.stubGlobal('fetch', fetch)
  const controller = new AbortController()
  await getSupportInbox('token', controller.signal)
  const urls = fetch.mock.calls.map(([url]) => new URL(url, 'http://localhost'))
  expect(urls[0].pathname).toBe('/api/admin/conversations/unassigned')
  expect(urls[1].pathname).toBe('/api/admin/conversations/assigned')
  expect(urls[1].searchParams.get('status')).toBe('Open')
  expect(urls.every((url) => url.searchParams.get('page_size') === '100')).toBe(true)
  expect(fetch.mock.calls.every(([, options]) => options.signal === controller.signal && options.headers.Authorization === 'Bearer token')).toBe(true)
  await getSupportPage('token', 'active', 2, controller.signal)
  const next = new URL(fetch.mock.calls.at(-1)[0], 'http://localhost')
  expect(next.searchParams.get('page')).toBe('2')
  expect(next.searchParams.get('status')).toBe('Open')
})

test('admins read every customer being helped instead of only their own chats', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ Items: [], Total: 0, Page: 1, PageSize: 100 })))
  vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal
  await getSupportInbox('token', signal, 'Admin')
  await getSupportPage('token', 'active', 2, signal, 'Admin')
  const urls = fetch.mock.calls.map(([url]) => new URL(url, 'http://localhost'))
  expect(urls.map((url) => url.pathname)).toEqual(['/api/admin/conversations/unassigned', '/api/admin/conversations/active', '/api/admin/conversations/active'])
  expect(urls[2].searchParams.get('page')).toBe('2')
})

test('chat writes use server-assigned identities and never send client ownership/status fields', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({})))
  vi.stubGlobal('fetch', fetch)
  await claimSupportConversation('token', 'conversation/id')
  await sendSupportMessage('token', 'conversation/id', 'Phản hồi')
  await closeSupportConversation('token', 'conversation/id')
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/admin/conversations/conversation%2Fid/claim', '/api/admin/conversations/conversation%2Fid/messages', '/api/admin/conversations/conversation%2Fid/close'])
  expect(fetch.mock.calls.every(([, options]) => options.method === 'POST')).toBe(true)
  expect(fetch.mock.calls[0][1].body).toBeUndefined()
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ MessageType: 'Text', Content: 'Phản hồi' })
  expect(fetch.mock.calls[2][1].body).toBeUndefined()
})

test('history, Admin all, summary, cursor window and read operations use separate authorized endpoints', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ Items: [], Total: 0 })))
  vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal
  await getSupportPage('token', 'closed', 1, signal, 'Staff')
  await getSupportPage('token', 'closed', 1, signal, 'Admin')
  await getSupportPage('token', 'all', 1, signal, 'Admin')
  expect(fetch.mock.calls.slice(0, 3).map(([url]) => url)).toEqual([
    '/api/admin/conversations/assigned?status=Closed&page=1&page_size=100',
    '/api/admin/conversations?status=Closed&page=1&page_size=100',
    '/api/admin/conversations?page=1&page_size=100',
  ])
  await getSupportConversation('token', 'c1', signal)
  expect(fetch.mock.calls.at(-1)[0]).toBe('/api/admin/conversations/c1/summary')
  await getSupportMessages('token', 'c1', { after_sent_at: '2026-10-16T08:00:00Z', after_message_id: 'm1' }, signal)
  const url = new URL(fetch.mock.calls.at(-1)[0], 'http://localhost')
  expect(url.pathname).toBe('/api/admin/conversations/c1/message-window')
  expect(url.searchParams.get('limit')).toBe('50')
  expect(url.searchParams.get('after_sent_at')).toBe('2026-10-16T08:00:00Z')
  await markSupportRead('token', 'c1', ['m1'])
  const [path, options] = fetch.mock.calls.at(-1)
  expect(path).toBe('/api/admin/conversations/c1/read')
  expect(options.method).toBe('POST')
  expect(JSON.parse(options.body)).toEqual({ MessageIds: ['m1'] })
})
