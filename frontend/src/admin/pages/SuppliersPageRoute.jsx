import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const SuppliersPage = lazy(() => import('./SuppliersPage.jsx'))

export default function SuppliersPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang nhà cung cấp…" />}><SuppliersPage /></Suspense>
}
