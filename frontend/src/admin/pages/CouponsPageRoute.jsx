import { lazy, Suspense } from 'react'
import { useOutletContext } from 'react-router-dom'
import { LoadingState } from '../../components/shared/index.js'
const CouponsPage = lazy(() => import('./CouponsPage.jsx'))
export default function CouponsPageRoute() {
  const { visit } = useOutletContext()
  return <Suspense fallback={<LoadingState label="Đang tải mã giảm giá…" />}><CouponsPage key={visit} /></Suspense>
}
