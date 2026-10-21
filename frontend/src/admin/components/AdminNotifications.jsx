import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Button, EmptyState, ErrorState, LoadingState, Pagination } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { formatDateTime } from '../../lib/format.js'
import { markAllNotificationsRead, markNotificationRead } from '../../services/api/admin.js'
import bell from '../../assets/admin/notification-bell.svg'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { notificationTarget } from '../lib/notifications.js'
import './AdminNotifications.css'

export default function AdminNotifications({ icon = bell, navigateToPage = false }) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [filter, setFilter] = useState('all')
  const [container, setContainer] = useState(null)
  const [busy, setBusy] = useState(false)
  const [failures, setFailures] = useState([])
  const root = useRef(null)
  const trigger = useRef(null)
  const marking = useRef(new Map()), mounted = useRef(false), navigation = useRef(0)
  const navigate = useNavigate(), location = useLocation(), currentLocation = useRef(location.key)
  const pageView = navigateToPage && location.pathname === '/admin/notifications'
  const expanded = pageView || open
  const pageSize = pageView ? 20 : 5
  useEffect(() => {
    if (!pageView) return
    const frame = requestAnimationFrame(() => setContainer(document.getElementById('admin-notifications-page')))
    return () => cancelAnimationFrame(frame)
  }, [pageView])
  useEffect(() => { currentLocation.current = location.key }, [location.key])
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const { withAccessToken, permissions } = useInternalAuth()
  const count = useAdminQuery('/users/me/notifications/unread-count', {}, true, { keepDataOnRefresh: true })
  const list = useAdminQuery('/users/me/notifications', { page, page_size: pageSize, is_read: pageView && filter === 'unread' ? false : undefined }, expanded)
  if (pageView && list.data && page > 1 && (page - 1) * pageSize >= list.data.Total) setPage(Math.max(1, Math.ceil(list.data.Total / pageSize)))
  const refreshCount = count.refresh, refreshList = list.refresh
  useEffect(() => {
    const refresh = () => { refreshCount(); if (expanded) refreshList() }
    const timer = window.setInterval(refresh, 60000)
    window.addEventListener('focus', refresh)
    window.addEventListener('admin-order-updated', refresh)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); window.removeEventListener('admin-order-updated', refresh) }
  }, [refreshCount, refreshList, expanded])
  useEffect(() => {
    if (!open || pageView) return
    const outside = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    const escape = (event) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus() } }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [open, pageView])

  function mark(id) {
    const key = id ?? '*'
    if (marking.current.has(key)) return marking.current.get(key)
    setBusy(true)
    const operation = (async () => {
      await Promise.resolve() // Install the per-notification lock before invoking the API.
      try {
        const result = await withAccessToken((token) => id ? markNotificationRead(token, id) : markAllNotificationsRead(token))
        if (mounted.current) {
          setFailures(previous => previous.filter(item => item.key !== key))
          count.refresh(); list.refresh()
        }
        return { ok: true, notification: result }
      } catch (failure) {
        if (mounted.current) setFailures(previous => [...previous.filter(item => item.key !== key), { key, id, message: failure.message || 'Vui lòng kiểm tra kết nối và thử lại.' }])
        return { ok: false }
      } finally {
        marking.current.delete(key)
        if (mounted.current) setBusy(marking.current.size > 0)
      }
    })()
    marking.current.set(key, operation)
    return operation
  }

  async function openNotification(event, item, target) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    const version = ++navigation.current, origin = currentLocation.current
    setOpen(false)
    if (item.NotificationType === 'Chat' && item.ReferenceType === 'Conversation') {
      // The queue may have changed since the dropdown loaded. The read response
      // contains the current safe target, including for an already-read alert.
      const result = await mark(item.NotificationId)
      if (!mounted.current || navigation.current !== version || currentLocation.current !== origin) return
      const destination = result.ok && result.notification?.NotificationId
        ? notificationTarget(result.notification, permissions) : '/admin/support'
      if (destination) navigate(destination)
    } else {
      navigate(target)
      if (!item.IsRead) void mark(item.NotificationId)
    }
  }

  const failure = failures[0]

  const panel = <section id="admin-notifications" aria-label="Danh sách thông báo" className={pageView ? 'admin-notifications-page' : 'absolute top-[52px] right-0 z-30 w-[360px] max-w-[calc(100vw-32px)] rounded-[14px] border border-admin-border bg-white p-4 text-admin-text shadow-lg max-[600px]:fixed max-[600px]:top-4 max-[600px]:right-4 max-[600px]:max-h-[calc(100dvh-32px)] max-[600px]:overflow-y-auto'}>
      <header className="flex items-center justify-between gap-3"><h2 className="text-base font-semibold">Thông báo</h2>
        <Button variant="ghost" size="sm" disabled={busy || !count.data?.Count} onClick={() => mark()}>Đọc tất cả</Button>
      </header>
      {pageView && <><p className="mb-4 text-sm text-admin-muted">Cập nhật công việc và các thông tin dành cho bạn.</p>
        <div className="mb-4 flex gap-2" role="group" aria-label="Lọc thông báo">
          {[['all', 'Tất cả'], ['unread', 'Chưa đọc']].map(([value, label]) => <button type="button" key={value}
            className="rounded-full border border-admin-border bg-white px-4 py-2 text-sm text-admin-text"
            aria-pressed={filter === value} disabled={busy} onClick={() => { setFilter(value); setPage(1) }}>{label}</button>)}
        </div></>}
      {count.error && <ErrorState title="Không cập nhật được thông báo" message={count.error} onRetry={() => { count.refresh(); list.refresh() }} className="py-4" />}
      {list.loading ? <LoadingState label="Đang tải thông báo…" className="py-8" /> : list.error ? <ErrorState message={list.error} onRetry={list.refresh} className="py-6" /> : !list.data?.Items.length ? <EmptyState title={pageView && filter === 'unread' ? 'Bạn đã đọc hết thông báo.' : 'Chưa có thông báo.'} headingLevel={3} className="py-10 [&_h3]:text-sm" /> : <ul className={pageView ? 'admin-notification-list' : 'my-3 max-h-[350px] overflow-y-auto'}>
        {list.data.Items.map((item) => {
          const target = notificationTarget(item, permissions)
          const queueAlert = item.NotificationType === 'Chat' && item.ReferenceType === 'Conversation' && item.ActionUrl === `/admin/support?conversation=${item.ReferenceId}`
          const href = queueAlert ? '/admin/support' : target
          const content = <><h3 className="text-sm font-semibold">{item.Title}</h3><p className="mt-1 text-xs leading-relaxed text-admin-muted">{item.Content}</p><time dateTime={item.CreatedAt} className="mt-1 block text-[10px] text-admin-muted">{formatDateTime(item.CreatedAt)}</time></>
          return <li key={item.NotificationId} className={pageView ? 'admin-notification-row' : `border-b border-admin-border p-3 last:border-0 ${item.IsRead ? '' : 'bg-admin-soft'}`}>
          {target ? <Link to={href} aria-label={'Mở thông báo: ' + item.Title} className="block rounded-sm hover:text-admin-blue" onClick={(event) => void openNotification(event, item, target)}>{content}</Link> : content}
          {pageView && <span className="mt-2 block text-xs text-admin-muted">{item.IsRead ? 'Đã đọc' : 'Chưa đọc'}</span>}
          <div className="mt-2 flex items-center justify-between gap-2">
            {target && <Link className="text-xs text-admin-blue hover:underline" to={href} onClick={(event) => void openNotification(event, item, target)}>Xem chi tiết</Link>}
            {!item.IsRead && <Button variant="ghost" size="sm" disabled={busy} onClick={() => mark(item.NotificationId)}>Đánh dấu đã đọc</Button>}
          </div>
        </li>})}
      </ul>}
      <Pagination page={page} pageSize={pageSize} total={list.data?.Total ?? 0} onPageChange={setPage} disabled={busy || list.loading} />
    </section>

  return <div ref={root} className="relative shrink-0">
    <button ref={trigger} type="button" aria-label="Thông báo" aria-expanded={navigateToPage ? undefined : open} aria-controls={!navigateToPage && open ? 'admin-notifications' : undefined}
      className="relative grid size-[42px] cursor-pointer place-items-center rounded-[10px] border-0 bg-transparent"
      aria-busy={busy || undefined} onClick={() => { if (navigateToPage) { setOpen(false); count.refresh(); navigate('/admin/notifications'); return } setOpen(value => !value); if (!open) count.refresh() }}>
      <img src={icon} width="24" height="24" alt="" />
      {count.data?.Count > 0 && <span className="absolute top-1.5 right-2 size-2 rounded-full bg-admin-red"><span className="sr-only">{count.data.Count} thông báo chưa đọc</span></span>}
    </button>
    {pageView ? container && createPortal(panel, container) : open && panel}
    {failure && <section role="alert" aria-label="Không đánh dấu được thông báo" className="fixed right-4 bottom-4 z-[60] w-[360px] max-w-[calc(100vw-32px)] rounded-xl border border-red-200 bg-white p-4 text-admin-text shadow-lg">
      <h2 className="text-sm font-semibold text-admin-red">Không đánh dấu được thông báo đã đọc</h2>
      <p className="mt-2 text-sm">{failure.message}</p>
      <div className="mt-3 flex justify-end gap-2"><Button size="sm" variant="secondary" onClick={() => setFailures(previous => previous.filter(item => item.key !== failure.key))}>Đóng</Button><Button size="sm" disabled={busy} onClick={() => void mark(failure.id)}>Thử lại</Button></div>
    </section>}
  </div>
}
