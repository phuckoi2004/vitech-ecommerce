import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const BrandsPage = lazy(() => import('./BrandsPage.jsx'))

export default function BrandsPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang thương hiệu…" />}><BrandsPage /></Suspense>
}
