import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const PaymentMethodWorkspacePage = lazy(() => import('./PaymentMethodWorkspacePage.jsx'))
export default function PaymentMethodWorkspacePageRoute({ mode }) {
  return <Suspense fallback={<LoadingState label="Đang tải trang phương thức thanh toán…" />}><PaymentMethodWorkspacePage mode={mode} /></Suspense>
}
