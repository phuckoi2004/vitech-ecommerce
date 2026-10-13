import { ADMIN_HOME_PATH, ADMIN_PROFILE_PATH, ADMIN_USERS_PATH } from './paths.js'

// Sidebar entries. `permission` is a code from the session's permission list (backend app/core/rbac.py, returned by
// /auth/login, /auth/refresh and /auth/me); it only hides the entry, the backend still enforces every request.
export const ADMIN_MENU = [
  { id: 'overview', label: 'Tổng quan', path: ADMIN_HOME_PATH },
  { id: 'accounts', label: 'Quản lý tài khoản', path: ADMIN_USERS_PATH, permission: 'users:read' },
]

// Opened from the account button in the top bar, not from the menu.
export const ADMIN_PROFILE_ITEM = { id: 'profile', label: 'Thông tin cá nhân', path: ADMIN_PROFILE_PATH }

export function visibleMenu(permissions) {
  return ADMIN_MENU.filter((item) => !item.permission || permissions.includes(item.permission))
}
