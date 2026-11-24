import { lazy, Suspense } from 'react'
import LoadingState from './LoadingState.jsx'

// Route definitions remain synchronous; each page's code and styles load only when it is opened.
export function lazyPage(load, exportName = 'default') {
  const Page = lazy(() => load().then((module) => ({ default: module[exportName] })))
  return function DeferredPage(props) {
    return <Suspense fallback={<LoadingState label="Đang tải trang…" />}><Page {...props} /></Suspense>
  }
}
