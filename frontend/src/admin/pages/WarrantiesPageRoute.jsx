import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const WarrantiesPage = lazy(() => import('./WarrantiesPage.jsx'))
export default function WarrantiesPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang bảo hành…" />}><WarrantiesPage /></Suspense>
}
