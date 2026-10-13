import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { buttonClassName } from './buttonStyles.js'
import EmptyState from './EmptyState.jsx'

// 404 for unknown URLs. The customer version renders inside the customer layout; the internal one stands alone.
export default function NotFoundPage({ area = 'customer' }) {
  const internal = area === 'admin'

  useEffect(() => {
    document.title = 'Không tìm thấy trang | VieTech'
  }, [])

  const content = <EmptyState headingLevel={1} title="Không tìm thấy trang"
    description="Đường dẫn không tồn tại hoặc đã được thay đổi. Vui lòng kiểm tra lại địa chỉ."
    action={<Link className={buttonClassName()} to={internal ? '/admin' : '/'}>
      {internal ? 'Về trang quản trị' : 'Về trang chủ'}
    </Link>} />

  return internal ? <main className="flex min-h-dvh items-center justify-center bg-surface-muted">{content}</main> : content
}
