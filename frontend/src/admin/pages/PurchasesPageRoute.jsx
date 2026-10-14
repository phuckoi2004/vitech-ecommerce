import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'
const PurchasesPage = lazy(() => import('./PurchasesPage.jsx'))
export default function PurchasesPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang nhập hàng…" />}><PurchasesPage /></Suspense>
}
