import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'

const PATH = '/admin/banners'
const bannerPath = (id) => PATH + '/' + encodeURIComponent(id)
// This endpoint returns the complete, ordered array, rather than a paginated response.
export const getBannerDirectory = (token, signal) => getAdminData(token, PATH, {}, signal)
export const createBanner = (accessToken, body) => request(PATH, { method: 'POST', accessToken, body })
export const updateBanner = (accessToken, id, body) => request(bannerPath(id), { method: 'PATCH', accessToken, body })
export const activateBanner = (accessToken, id) => request(bannerPath(id) + '/activate', { method: 'POST', accessToken })
export const deactivateBanner = (accessToken, id) => request(bannerPath(id) + '/deactivate', { method: 'POST', accessToken })
export const deleteBanner = (accessToken, id) => request(bannerPath(id), { method: 'DELETE', accessToken })
