import { vi } from 'vitest'

const DEFAULT_PERMISSIONS = {
  Admin: ['admin.portal', 'profile:read', 'profile:update', 'users:read', 'users:manage'],
  Staff: ['admin.portal', 'profile:read', 'profile:update', 'orders:view'],
  Customer: ['customer.portal', 'profile:read', 'profile:update'],
}

// An AuthContext value for route and page tests: `role` null means signed out.
export function makeAuth({ role = null, permissions, ...overrides } = {}) {
  const user = role
    ? { UserId: `${role}-id`, Role: role, FullName: `${role} for test`, PhoneNumber: '0912345678', Email: `${role.toLowerCase()}@example.com`, AvatarUrl: null }
    : null
  const granted = user ? permissions ?? DEFAULT_PERMISSIONS[role] ?? [] : []
  const area = role === 'Customer' ? 'customer' : ['Staff', 'Admin'].includes(role) ? 'internal' : null
  return {
    status: user ? 'authenticated' : 'anonymous',
    session: user ? { user, access_token: 'access-for-test', csrf_token: 'csrf-for-test', permissions: granted } : null,
    user,
    role,
    area,
    isCustomer: area === 'customer',
    isInternal: area === 'internal',
    permissions: granted,
    accessToken: user ? 'access-for-test' : null,
    hasPermission: (permission) => granted.includes(permission),
    loading: false,
    sessionReady: true,
    error: '',
    notice: '',
    endReason: null,
    signInInternal: vi.fn(),
    signInCustomer: vi.fn(),
    signOut: vi.fn(async () => {}),
    withAccessToken: vi.fn((call) => call('access-for-test')),
    updateUser: vi.fn(),
    endSession: vi.fn(),
    ...overrides,
  }
}
