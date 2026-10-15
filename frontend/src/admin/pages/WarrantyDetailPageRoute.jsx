import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const WarrantyDetailPage = lazy(() => import('./WarrantyDetailPage.jsx'))
export default function WarrantyDetailPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang chi tiết bảo hành…" />}><WarrantyDetailPage /></Suspense>
}
