import { afterEach, expect, test, vi } from 'vitest'
import { claimSupportConversation, closeSupportConversation, getSupportInbox, getSupportPage, sendSupportMessage } from './support.js'

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
