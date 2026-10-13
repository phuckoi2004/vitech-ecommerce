import { adminRoutes } from './admin/routes/index.jsx'
import RouteErrorPage from './components/shared/RouteErrorPage.jsx'
import { customerRoutes } from './customer/routes/index.jsx'

// All routes of the app. Used by the browser router (App.jsx) and by memory routers in tests.
export const appRoutes = [
  { errorElement: <RouteErrorPage />, children: [...adminRoutes, ...customerRoutes] },
]
