import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'

const PATH = '/admin/conversations'
const conversationPath = (id) => PATH + '/' + encodeURIComponent(id)
// Admins oversee every customer being helped (with who is helping); staff see the chats they claimed.
const activeList = (token, page, signal, role) => role === 'Admin'
  ? getAdminData(token, PATH + '/active', { page, page_size: 100 }, signal)
  : getAdminData(token, PATH + '/assigned', { status: 'Open', page, page_size: 100 }, signal)
export async function getSupportInbox(token, signal, role = 'Staff') {
  const [waiting, active] = await Promise.all([
    getAdminData(token, PATH + '/unassigned', { page: 1, page_size: 100 }, signal),
    activeList(token, 1, signal, role),
  ])
  return { waiting, active }
}
export function getSupportPage(token, tab, page, signal, role = 'Staff') {
  if (tab === 'active') return activeList(token, page, signal, role)
  const all = tab === 'all' || (tab === 'closed' && role === 'Admin')
  const path = all ? PATH : PATH + (tab === 'waiting' ? '/unassigned' : '/assigned')
  return getAdminData(token, path, { ...(tab === 'active' ? { status: 'Open' } : tab === 'closed' ? { status: 'Closed' } : {}), page, page_size: 100 }, signal)
}
export const getSupportConversation = (token, id, signal) => getAdminData(token, conversationPath(id) + '/summary', {}, signal)
export const getSupportMessages = (token, id, query, signal) => getAdminData(token, conversationPath(id) + '/message-window', { limit: 50, ...query }, signal)
export const markSupportRead = (accessToken, id, ids) => request(conversationPath(id) + '/read', { method: 'POST', accessToken, body: { MessageIds: ids } })
export const claimSupportConversation = (accessToken, id) => request(conversationPath(id) + '/claim', { method: 'POST', accessToken })
export const sendSupportMessage = (accessToken, id, content) => request(conversationPath(id) + '/messages', { method: 'POST', accessToken, body: { MessageType: 'Text', Content: content } })
export const closeSupportConversation = (accessToken, id) => request(conversationPath(id) + '/close', { method: 'POST', accessToken })
