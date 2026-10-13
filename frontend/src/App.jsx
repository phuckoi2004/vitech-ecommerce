import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider.jsx'
import { appRoutes } from './routes.jsx'
import './App.css'

const router = createBrowserRouter(appRoutes)

// /admin/* is the internal area for Staff and Admin; everything else is the customer site.
export default function App() {
  return <AuthProvider>
    <RouterProvider router={router} />
  </AuthProvider>
}
