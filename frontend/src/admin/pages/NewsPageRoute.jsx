import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const NewsPage = lazy(() => import('./NewsPage.jsx'))
export default function NewsPageRoute() {
  return <Suspense fallback={<LoadingState label="Đang tải trang tin tức…" />}><NewsPage /></Suspense>
}
