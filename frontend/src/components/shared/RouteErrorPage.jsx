import { useEffect } from 'react'
import ErrorState from './ErrorState.jsx'

// Shown by the router when a page throws while rendering; details stay in the browser console.
export default function RouteErrorPage() {
  useEffect(() => {
    document.title = 'Đã có lỗi | VieTech'
  }, [])

  return <main className="flex min-h-dvh items-center justify-center bg-surface-muted">
    <ErrorState title="Đã có lỗi khi hiển thị trang" message="Vui lòng tải lại trang. Nếu lỗi vẫn tiếp diễn, hãy thử lại sau."
      onRetry={() => window.location.reload()} retryLabel="Tải lại trang" />
  </main>
}
