// Session helpers shared by the AuthProvider, route guards and login pages.

export const CUSTOMER_ROLE = 'Customer'
export const INTERNAL_ROLES = new Set(['Staff', 'Admin'])

// Which portal a session belongs to: 'customer', 'internal', or null for anything else.
export function sessionArea(session) {
  const role = session?.user?.Role
  if (role === CUSTOMER_ROLE) return 'customer'
  if (INTERNAL_ROLES.has(role)) return 'internal'
  return null
}

const ORIGIN = 'https://vietech.invalid'

function isAdminPath(pathname) {
  return pathname === '/admin' || pathname.startsWith('/admin/')
}

// A `next` value we may navigate to after sign-in: same-site path only (no scheme, host or `//`),
// inside the area of the login page and never back to a sign-in page. Otherwise null.
export function safeNext(value, area) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || /[\\\s]/.test(value)) return null
  let url
  try {
    url = new URL(value, ORIGIN)
  } catch {
    return null
  }
  if (url.origin !== ORIGIN) return null
  const path = url.pathname
  const target = `${path}${url.search}${url.hash}`
  if (area === 'admin') {
    return isAdminPath(path) && !['/admin/login', '/admin/forgot-password'].includes(path) ? target : null
  }
  return !isAdminPath(path) && !['/dang-nhap', '/dang-ky', '/quen-mat-khau'].includes(path) ? target : null
}

// Query string that sends the visitor back to `location` after signing in.
export function nextQuery(location) {
  return `?next=${encodeURIComponent(`${location.pathname}${location.search}`)}`
}
