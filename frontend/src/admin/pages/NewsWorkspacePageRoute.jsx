import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const NewsWorkspacePage = lazy(() => import('./NewsWorkspacePage.jsx'))
export default function NewsWorkspacePageRoute({ mode }) {
  return <Suspense fallback={<LoadingState label="Đang tải trang tin tức…" />}><NewsWorkspacePage mode={mode} /></Suspense>
}
