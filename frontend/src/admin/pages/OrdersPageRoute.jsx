import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const OrdersPage = lazy(() => import('./OrdersPage.jsx'))

export default function OrdersPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang đơn hàng…" />}><OrdersPage /></Suspense>
}
