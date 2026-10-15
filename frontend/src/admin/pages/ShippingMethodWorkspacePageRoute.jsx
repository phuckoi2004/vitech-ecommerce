import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'
const ShippingMethodWorkspacePage = lazy(() => import('./ShippingMethodWorkspacePage.jsx'))
export default function ShippingMethodWorkspacePageRoute({ mode }) {
  return <Suspense fallback={<LoadingState label="Đang tải phương thức vận chuyển…" />}><ShippingMethodWorkspacePage mode={mode} /></Suspense>
}
