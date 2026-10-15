import { lazy, Suspense } from 'react'
import { useOutletContext } from 'react-router-dom'
import { LoadingState } from '../../components/shared/index.js'
const ShippingMethodsPage = lazy(() => import('./ShippingMethodsPage.jsx'))
export default function ShippingMethodsPageRoute() {
  const { visit } = useOutletContext()
  return <Suspense fallback={<LoadingState label="Đang tải phương thức vận chuyển…" />}><ShippingMethodsPage key={visit} /></Suspense>
}
