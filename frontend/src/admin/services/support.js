import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'

const PATH = '/admin/conversations'
const conversationPath = (id) => PATH + '/' + encodeURIComponent(id)
export async function getSupportInbox(token, signal) {
  const [waiting, active] = await Promise.all([
    getAdminData(token, PATH + '/unassigned', { page: 1, page_size: 100 }, signal),
    getAdminData(token, PATH + '/assigned', { status: 'Open', page: 1, page_size: 100 }, signal),
  ])
  return { waiting, active }
}
export const getSupportPage = (token, tab, page, signal) => getAdminData(token, PATH + (tab === 'active' ? '/assigned' : '/unassigned'), { ...(tab === 'active' ? { status: 'Open' } : {}), page, page_size: 100 }, signal)
export const getSupportConversation = (token, id, signal) => getAdminData(token, conversationPath(id), {}, signal)
export const claimSupportConversation = (accessToken, id) => request(conversationPath(id) + '/claim', { method: 'POST', accessToken })
export const sendSupportMessage = (accessToken, id, content) => request(conversationPath(id) + '/messages', { method: 'POST', accessToken, body: { MessageType: 'Text', Content: content } })
export const closeSupportConversation = (accessToken, id) => request(conversationPath(id) + '/close', { method: 'POST', accessToken })
