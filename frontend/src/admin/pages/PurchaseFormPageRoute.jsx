import { lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import { LoadingState } from '../../components/shared/index.js'

const PurchaseFormPage = lazy(() => import('./PurchaseFormPage.jsx'))

export default function PurchaseFormPageRoute() {
  const { purchaseId } = useParams()
  return <Suspense fallback={<LoadingState label="Đang tải form phiếu nhập…" />}><PurchaseFormPage key={purchaseId ?? 'new'} /></Suspense>
}
