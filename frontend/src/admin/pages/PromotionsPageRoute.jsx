import { lazy, Suspense } from 'react'
import { useOutletContext } from 'react-router-dom'
import { LoadingState } from '../../components/shared/index.js'
const PromotionsPage = lazy(() => import('./PromotionsPage.jsx'))
export default function PromotionsPageRoute() {
  const { visit } = useOutletContext()
  return <Suspense fallback={<LoadingState label="Đang tải khuyến mãi…" />}><PromotionsPage key={visit} /></Suspense>
}
