import { lazy, Suspense } from 'react'
import { LoadingState } from '../../components/shared/index.js'

const BannerWorkspacePage = lazy(() => import('./BannerWorkspacePage.jsx'))
export default function BannerWorkspacePageRoute({ mode }) {
  return <Suspense fallback={<LoadingState label="Đang tải trang banner…" />}><BannerWorkspacePage mode={mode} /></Suspense>
}
