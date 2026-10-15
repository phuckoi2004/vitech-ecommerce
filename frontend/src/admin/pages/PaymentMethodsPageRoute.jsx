import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const PaymentMethodsPage = lazy(() => import('./PaymentMethodsPage.jsx'))
export default function PaymentMethodsPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang thanh toán…" />}><PaymentMethodsPage /></Suspense>
}
