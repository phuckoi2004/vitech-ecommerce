import RequireInternal from '../../auth/RequireInternal.jsx'
import NotFoundPage from '../../components/shared/NotFoundPage.jsx'
import AdminAuthPage from '../pages/AdminAuthPage.jsx'
import AdminHomePage from '../pages/AdminHomePage.jsx'
import { AdminProfileSection, AdminUsersSection } from '../pages/AdminSections.jsx'
import { ADMIN_FORGOT_PASSWORD_PATH, ADMIN_HOME_PATH, ADMIN_LOGIN_PATH } from './paths.js'

// Internal area for Staff/Admin (English URLs). Unknown /admin/* URLs show the 404 page, signed in or not.
export const adminRoutes = [
  { path: ADMIN_LOGIN_PATH, element: <AdminAuthPage page="login" /> },
  { path: ADMIN_FORGOT_PASSWORD_PATH, element: <AdminAuthPage page="reset" /> },
  {
    path: ADMIN_HOME_PATH,
    element: <RequireInternal><AdminHomePage /></RequireInternal>,
    children: [
      { index: true, element: null },
      { path: 'users', element: <AdminUsersSection /> },
      { path: 'profile', element: <AdminProfileSection /> },
    ],
  },
  { path: '/admin/*', element: <NotFoundPage area="admin" /> },
]
