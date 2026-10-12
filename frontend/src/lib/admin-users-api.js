import { apiRequest } from './auth-api.js'

// filters: { page, pageSize, search, role, status } where status is Active | Locked | Deleted.
export function listUsers(accessToken, { page = 1, pageSize = 20, search = '', role = '', status = '' } = {}) {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (search.trim()) query.set('search', search.trim())
  if (role) query.set('role', role)
  if (status === 'Deleted') query.set('deleted_only', 'true')
  else if (status) query.set('account_status', status)
  return apiRequest(`/admin/users?${query}`, { method: 'GET', accessToken })
}

export function getUser(accessToken, userId) {
  return apiRequest(`/admin/users/${userId}?include_deleted=true`, { method: 'GET', accessToken })
}

export function getUserDefaultAddress(accessToken, userId) {
  return apiRequest(`/admin/users/${userId}/default-address`, { method: 'GET', accessToken })
}

export function createStaff(accessToken, values) {
  return apiRequest('/admin/users', { body: { ...values, Role: 'Staff' }, accessToken })
}

// Also locks ({ AccountStatus: 'Locked', LockReason, LockedUntil }) and unlocks ({ AccountStatus: 'Active' }).
export function updateUser(accessToken, userId, changes) {
  return apiRequest(`/admin/users/${userId}`, { method: 'PATCH', body: changes, accessToken })
}

export async function deleteUser(accessToken, userId) {
  await apiRequest(`/admin/users/${userId}`, { method: 'DELETE', accessToken })
}
