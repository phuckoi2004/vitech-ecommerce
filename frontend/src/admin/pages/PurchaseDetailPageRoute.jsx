import { lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import { LoadingState } from '../../components/shared/index.js'

const PurchaseDetailPage = lazy(() => import('./PurchaseDetailPage.jsx'))

export default function PurchaseDetailPageRoute() {
  const { purchaseId } = useParams()
  return <Suspense fallback={<LoadingState label="Đang tải chi tiết phiếu nhập…" />}><PurchaseDetailPage key={purchaseId} /></Suspense>
}
