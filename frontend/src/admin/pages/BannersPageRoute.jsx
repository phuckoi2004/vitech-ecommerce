import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const BannersPage = lazy(() => import('./BannersPage.jsx'))
export default function BannersPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang banner…" />}><BannersPage /></Suspense>
}
