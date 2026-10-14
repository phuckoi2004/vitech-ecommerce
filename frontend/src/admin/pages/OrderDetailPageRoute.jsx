import { lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import { LoadingState } from '../../components/shared/index.js'

const OrderDetailPage = lazy(() => import('./OrderDetailPage.jsx'))

export default function OrderDetailPageRoute() {
  const { orderId } = useParams()
  return <Suspense fallback={<LoadingState label="Đang tải chi tiết đơn hàng…" />}><OrderDetailPage key={orderId} /></Suspense>
}
