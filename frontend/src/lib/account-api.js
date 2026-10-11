import { apiRequest } from './auth-api.js'

export const AVATAR_MAX_BYTES = 2 * 1024 * 1024
export const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export function getProfile(accessToken) {
  return apiRequest('/users/me', { method: 'GET', accessToken })
}

// Send only the fields that changed; the backend rejects an empty update.
export function updateProfile(accessToken, changes) {
  return apiRequest('/users/me', { method: 'PATCH', body: changes, accessToken })
}

export function uploadAvatar(accessToken, file) {
  return apiRequest('/users/me/avatar', { method: 'PUT', file, accessToken })
}

export function getDefaultAddress(accessToken) {
  return apiRequest('/users/me/default-address', { method: 'GET', accessToken })
}

export function saveDefaultAddress(accessToken, address) {
  return apiRequest('/users/me/default-address', { method: 'PUT', body: address, accessToken })
}

export function changePassword(accessToken, currentPassword, newPassword, confirmPassword) {
  return apiRequest('/auth/change-password', {
    body: { CurrentPassword: currentPassword, NewPassword: newPassword, ConfirmPassword: confirmPassword },
    accessToken,
  })
}
