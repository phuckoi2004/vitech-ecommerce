import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const SupportPage = lazy(() => import('./SupportPage.jsx'))
export default function SupportPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang hỗ trợ khách hàng…" />}><SupportPage /></Suspense>
}
