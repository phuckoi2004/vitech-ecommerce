import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const ReturnsPage = lazy(() => import('./ReturnsPage.jsx'))
export default function ReturnsPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang đổi trả…" />}><ReturnsPage /></Suspense>
}
