import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Button from '../../components/shared/Button.jsx'
import EmptyState from '../../components/shared/EmptyState.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import Pagination from '../../components/shared/Pagination.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { getProduct } from '../../lib/catalog-api.js'
import { formatDateTime } from '../../lib/format.js'
import { HOME_PATH } from '../routes/paths.js'
import WishlistProductCard from '../components/WishlistProductCard.jsx'
import { readWishlistProducts } from '../hooks/useWishlistProduct.js'
import useNotificationData from '../hooks/useNotificationData.js'
import { customerNotificationTarget } from '../notifications.js'
import NotificationDetailDialog from '../components/NotificationDetailDialog.jsx'
import './ShoppingPages.css'

export function WishlistPage() {
  const send = useCustomerRequest()
  const { user } = useCustomerSession()
  const wishlist = useApiData(user ? `my-wishlist:${user.UserId}` : null, async (signal) => {
    const data = await readWishlistProducts(user.UserId, send, { signal })
    // Wishlist contains ProductSummary; price, photos and stock require the existing product detail endpoint.
    const Items = await Promise.all(data.Items.map(async (item) => {
      try { return { ...item, Product: await getProduct(item.ProductId ?? item.Product.ProductId, { signal }) } }
      catch (failure) {
        if (signal.aborted || failure.status !== 404) throw failure
        return { ...item, unavailable: true }
      }
    }))
    return { ...data, Items }
  })
  const { reload } = wishlist
  useEffect(() => {
    window.addEventListener('vietech-wishlist-changed', reload)
    return () => window.removeEventListener('vietech-wishlist-changed', reload)
  }, [reload])

  return <div className="shopping-page wishlist-page">
    <nav className="wishlist-breadcrumb" aria-label="Đường dẫn trang yêu thích"><Link to={HOME_PATH}>Trang chủ</Link><span aria-hidden="true">›</span><span aria-current="page">Sản phẩm yêu thích</span></nav>
    <header className="wishlist-heading"><h1>Sản phẩm yêu thích</h1>
      {!wishlist.loading && !wishlist.error && user && <span className="wishlist-count">{wishlist.data.Items.length} sản phẩm</span>}
    </header>
    {wishlist.loading || !user ? <LoadingState /> : wishlist.error ? <ErrorState message={wishlist.error} onRetry={wishlist.reload} />
      : !wishlist.data.Items.length ? <EmptyState className="wishlist-empty" title="Bạn chưa có sản phẩm yêu thích nào." />
        : <ul className="shopping-products wishlist-products">
          {wishlist.data.Items.map((item) => <li key={item.WishlistItemId}><WishlistProductCard product={item.Product} unavailable={item.unavailable} /></li>)}
        </ul>}
  </div>
}

export function NotificationsPage() {
  const send = useCustomerRequest()
  const { user } = useCustomerSession()
  const navigate = useNavigate()
  const location = useLocation()
  const [page, setPage] = useState(1)
  const notices = useNotificationData(user ? `my-notifications:${user.UserId}:${page}` : null, (signal) => send('/users/me/notifications', { query: { page, page_size: 20 }, signal }))
  const [busy, setBusy] = useState('')
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const lock = useRef(false), mounted = useRef(false), locationKey = useRef(location.key)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => { locationKey.current = location.key }, [location.key])
  async function mark(id, item, target) {
    if (lock.current) return false
    lock.current = true
    setBusy(id || 'all'); setError(null)
    try {
      await send(id ? `/users/me/notifications/${encodeURIComponent(id)}/read` : '/users/me/notifications/read-all', { method: 'POST' })
      window.dispatchEvent(new Event('vietech-notifications-changed'))
      return true
    } catch (failure) { if (mounted.current) setError({ id, item, target, message: failure.message }); return false }
    finally { lock.current = false; if (mounted.current) setBusy('') }
  }
  async function openNotification(item, target) {
    const origin = location.key
    if (!item.IsRead && !await mark(item.NotificationId, item, target)) return
    if (!mounted.current || locationKey.current !== origin) return
    if (target.kind === 'detail') setSelected(target)
    else navigate(target.to)
  }
  return <div className="shopping-page"><h1>Thông báo</h1>
    {error && <div role="alert" className="shopping-notice">{error.message} <button type="button" disabled={!!busy}
      onClick={() => error.target ? openNotification(error.item, error.target) : mark(error.id)}>Thử lại</button></div>}
    {notices.error && <ErrorState title="Không cập nhật được danh sách thông báo" message={notices.error} onRetry={notices.reload} />}
    {notices.loading ? <LoadingState /> : !notices.data ? null
      : !notices.data.Items.length ? <EmptyState title="Chưa có thông báo" /> : <>
        <Button variant="outline" loading={busy === 'all'} disabled={!!busy} onClick={() => mark()}>Đánh dấu tất cả đã đọc</Button>
        {notices.data.Items.map((item) => {
          const target = customerNotificationTarget(item)
          return <article className="shopping-line notification-item" key={item.NotificationId}>
          <div><h2>{target ? target.kind === 'link' ? <Link to={target.to} onClick={event => {
            if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
            event.preventDefault(); void openNotification(item, target)
          }}>{item.Title}</Link> : <button className="notification-open" type="button" disabled={!!busy} onClick={() => openNotification(item, target)}>{item.Title}</button> : item.Title}{!item.IsRead && ' · Chưa đọc'}</h2><p className="shopping-text">{item.Content}</p>
            <time dateTime={item.CreatedAt}>{formatDateTime(item.CreatedAt)}</time>
          </div>
          {!item.IsRead && <Button variant="outline" loading={busy === item.NotificationId} disabled={!!busy}
            onClick={() => mark(item.NotificationId)}>Đánh dấu đã đọc</Button>}
        </article>})}
        <Pagination page={page} pageSize={20} total={notices.data.Total} onPageChange={setPage} disabled={!!busy} />
      </>}
    {selected && <NotificationDetailDialog target={selected} onClose={() => setSelected(null)} />}
  </div>
}
