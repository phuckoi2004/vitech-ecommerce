import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const ReportsPage = lazy(() => import('./ReportsPage.jsx'))
export default function ReportsPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải báo cáo thống kê…" />}><ReportsPage /></Suspense>
}
