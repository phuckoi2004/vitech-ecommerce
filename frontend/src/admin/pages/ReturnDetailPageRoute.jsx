import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const ReturnDetailPage = lazy(() => import('./ReturnDetailPage.jsx'))
export default function ReturnDetailPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang chi tiết đổi trả…" />}><ReturnDetailPage /></Suspense>
}
