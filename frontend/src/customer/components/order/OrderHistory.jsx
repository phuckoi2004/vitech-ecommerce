import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import EmptyState from '../../../components/shared/EmptyState.jsx'
import Money from '../../../components/shared/Money.jsx'
import Pagination from '../../../components/shared/Pagination.jsx'
import useApiData from '../../../hooks/useApiData.js'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { formatDate } from '../../../lib/format.js'
import { listMyOrders } from '../../../lib/order-api.js'
import { formatStatus } from '../../../lib/status-labels.js'
import { HOME_PATH, orderPath, productReviewsPath } from '../../routes/paths.js'
import { historyFilters, historyQuery, ORDER_HISTORY_PAGE_SIZE, ORDER_TABS, orderItemsText, reviewProducts } from './orderHistory.js'
import { ORDER_STATUS } from './orderPayment.js'

// Code and dates apply on "Tìm kiếm"; the parent remounts this form when the applied values change (back/forward).
function OrderFilters({ filters, onApply }) {
  const [code, setCode] = useState(filters.code)
  const [from, setFrom] = useState(filters.from)
  const [to, setTo] = useState(filters.to)
  const [error, setError] = useState('')
  const [today] = useState(() => new Date().toLocaleDateString('en-CA'))

  function submit(event) {
    event.preventDefault()
    if (from && to && from > to) return setError('"Từ ngày" không được sau "Đến ngày".')
    setError('')
    onApply({ code: code.trim(), from, to })
  }

  return <form className="cacc-order-filters" role="search" aria-label="Tìm đơn hàng" onSubmit={submit} noValidate>
    <div className="cacc-field">
      <label className="cacc-field-label" htmlFor="cacc-order-code">Tìm theo mã đơn</label>
      <input id="cacc-order-code" className="cacc-input" maxLength={50} placeholder="VD: VT261021AB12CD" value={code}
        onChange={(event) => setCode(event.target.value)} />
    </div>
    <div className="cacc-field">
      <label className="cacc-field-label" htmlFor="cacc-order-from">Từ ngày</label>
      <input id="cacc-order-from" className="cacc-input" type="date" max={to || today} value={from}
        onChange={(event) => setFrom(event.target.value)} />
    </div>
    <div className="cacc-field">
      <label className="cacc-field-label" htmlFor="cacc-order-to">Đến ngày</label>
      <input id="cacc-order-to" className="cacc-input" type="date" min={from || undefined} max={today} value={to}
        onChange={(event) => setTo(event.target.value)} />
    </div>
    <button type="submit" className="cacc-button">Tìm kiếm</button>
    {error && <p className="cacc-notice cacc-order-filters-error" role="alert">{error}</p>}
  </form>
}

// Several products: a short list to pick from, closed by a click outside or Escape.
function ReviewMenu({ products, orderId }) {
  const menu = useRef(null)

  useEffect(() => {
    function close(event) {
      if (!menu.current?.open) return
      if (event.type === 'keydown' ? event.key === 'Escape' : !menu.current.contains(event.target)) menu.current.open = false
    }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', close)
    }
  }, [])

  return <details ref={menu} className="cacc-order-review">
    <summary className="cacc-button">Đánh giá sản phẩm</summary>
    <ul aria-label="Chọn sản phẩm để đánh giá">
      {products.map((product) => <li key={product.slug}><Link to={productReviewsPath(product.slug, orderId)}>{product.name}</Link></li>)}
    </ul>
  </details>
}

// One product goes straight to its reviews.
function ReviewAction({ products, orderId }) {
  if (products.length === 1) return <Link className="cacc-button" to={productReviewsPath(products[0].slug, orderId)}>Đánh giá sản phẩm</Link>
  return <ReviewMenu products={products} orderId={orderId} />
}

function OrderCard({ order }) {
  const products = reviewProducts(order)
  return <li className="cacc-order">
    <div className="cacc-order-info">
      <p className="cacc-order-code">{order.OrderCode} • {formatDate(order.OrderedAt)}</p>
      {order.SourceReturnRequestId && <p className="font-semibold text-red-600">Đơn đổi trả</p>}
      <p className="cacc-order-items">{orderItemsText(order.Items)}</p>
      <p className="cacc-order-meta">
        <span>Tổng tiền: <Money value={order.TotalAmount} /></span>
        <span>Trạng thái: <span className="cacc-order-status" data-status={order.OrderStatus}>
          {formatStatus(order.OrderStatus, ORDER_STATUS)}</span></span>
      </p>
    </div>
    <div className="cacc-order-actions">
      <Link className="cacc-button is-outline" to={orderPath(order.OrderId)} aria-label={`Xem chi tiết đơn ${order.OrderCode}`}>
        Xem chi tiết
      </Link>
      {products.length > 0 && <ReviewAction products={products} orderId={order.OrderId} />}
    </div>
  </li>
}

// "Lịch sử mua hàng" of the account page (Figma frame 245:439). Tab, code, dates and page live in the URL next to
// `section`, so returning from an order's page shows the same list.
export default function OrderHistory() {
  const { user, withAccessToken } = useCustomerSession()
  const [params, setParams] = useSearchParams()
  const filters = historyFilters(params)
  const query = historyQuery(filters)
  const orders = useApiData(`order-history:${user.UserId}:${JSON.stringify(query)}`, (signal) =>
    withAccessToken((token) => listMyOrders(token, query, { signal })))
  const filtered = Boolean(filters.tab || filters.code || filters.from || filters.to)

  // Empty values drop their key; every filter change starts again from the first page.
  function update(changes) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(changes)) {
        if (value) next.set(key, String(value))
        else next.delete(key)
      }
      return next
    })
  }

  const data = orders.data
  return <>
    <div className="cacc-panel-heading"><h1>Lịch sử mua hàng</h1></div>
    <div className="cacc-order-tabs" role="group" aria-label="Lọc theo trạng thái đơn hàng">
      {ORDER_TABS.map((tab) => <button key={tab.id || 'all'} type="button"
        className={`cacc-order-tab ${tab.id === filters.tab ? 'is-active' : ''}`} aria-pressed={tab.id === filters.tab}
        onClick={() => update({ status: tab.id, page: '' })}>{tab.label}</button>)}
    </div>
    <OrderFilters key={`${filters.code}|${filters.from}|${filters.to}`} filters={filters}
      onApply={(values) => update({ ...values, page: '' })} />
    {orders.loading ? <div className="cacc-loading is-compact" role="status"><span className="spinner" />Đang tải đơn hàng…</div>
      : orders.error ? <>
        <p className="cacc-notice" role="alert">{orders.error}</p>
        <button type="button" className="cacc-button is-outline cacc-order-retry" onClick={orders.reload}>Thử lại</button>
      </>
        : !data.Items.length ? data.Total > 0
          ? <EmptyState headingLevel={2} title="Trang này không còn đơn hàng"
            action={<button type="button" className="cacc-button is-outline" onClick={() => update({ page: '' })}>Về trang đầu</button>} />
          : filtered
            ? <EmptyState headingLevel={2} title="Không tìm thấy đơn hàng phù hợp" description="Hãy thử trạng thái, mã đơn hoặc khoảng ngày khác."
              action={<button type="button" className="cacc-button is-outline"
                onClick={() => update({ status: '', code: '', from: '', to: '', page: '' })}>Xóa bộ lọc</button>} />
            : <EmptyState headingLevel={2} title="Bạn chưa có đơn hàng nào" description="Các đơn hàng bạn đặt tại VieTech sẽ hiện ở đây."
              action={<Link className="cacc-button" to={HOME_PATH}>Mua sắm ngay</Link>} />
          : <>
            <ul className="cacc-orders" aria-label="Danh sách đơn hàng">
              {data.Items.map((order) => <OrderCard key={order.OrderId} order={order} />)}
            </ul>
            <div className="cacc-order-pages">
              <Pagination page={filters.page} pageSize={ORDER_HISTORY_PAGE_SIZE} total={data.Total} label="Phân trang đơn hàng"
                onPageChange={(page) => update({ page: page > 1 ? page : '' })} />
            </div>
          </>}
  </>
}
