import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const ReviewsPage = lazy(() => import('./ReviewsPage.jsx'))
export default function ReviewsPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang đánh giá…" />}><ReviewsPage /></Suspense>
}
