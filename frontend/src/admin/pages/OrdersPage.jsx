import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Pagination } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { formatDate } from '../../lib/format.js'
import AdminTable from '../components/AdminTable.jsx'
import OrderBadge from '../components/OrderBadge.jsx'
import OrderDialog from '../components/OrderDialog.jsx'
import { PRODUCT_CONTROL, ProductButton } from '../components/ProductUi.jsx'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { ORDER_NEXT, ORDER_PAGE_SIZE, ORDER_STATUSES, orderFilters, orderListSearch } from '../lib/orders.js'

function OrderSearch({ keyword, onSearch }) {
  const [value, setValue] = useState(keyword)
  const [source, setSource] = useState(keyword)
  if (source !== keyword) { setSource(keyword); setValue(keyword) }
  return <form role="search" className="flex items-end gap-2.5" onSubmit={(event) => { event.preventDefault(); onSearch(value.trim()) }}>
    <label className="flex w-[330px] flex-col gap-1.5 text-[11px] leading-normal font-semibold">Tìm kiếm
      <input type="search" aria-label="Tìm kiếm đơn hàng theo mã" placeholder="Tìm kiếm đơn hàng.." title="Tìm kiếm theo mã đơn hàng" maxLength={255} className={PRODUCT_CONTROL + ' h-10 rounded-lg! px-3 text-[10px]! font-normal placeholder:text-admin-muted'} value={value} onChange={(event) => setValue(event.target.value)} />
    </label>
    <ProductButton type="submit" className="mb-[5px] h-[31px]! rounded-[9px]! px-[13px]! text-[11px]!">Tìm kiếm</ProductButton>
  </form>
}

export default function OrdersPage() {
  const auth = useInternalAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const filter = orderFilters(params)
  const list = useAdminQuery('/admin/orders', { page: filter.page, page_size: ORDER_PAGE_SIZE, order_code: filter.keyword, order_status: filter.status })
  const [notice, setNotice] = useState('')
  const canUpdate = auth.permissions.includes('orders:update')
  const rows = list.data?.Items ?? []
  const total = list.data?.Total ?? 0
  const pages = Math.max(1, Math.ceil(total / ORDER_PAGE_SIZE))
  useEffect(() => {
    if (list.data && !list.loading && !list.error && filter.page > pages) setParams((previous) => {
      const next = new URLSearchParams(previous); next.set('page', String(pages)); return next
    }, { replace: true })
  }, [list.data, list.loading, list.error, filter.page, pages, setParams])

  function change(key, value) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'page') next.delete('page')
      return next
    })
  }
  function open(id, action) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (id) next.set('order', id)
      else next.delete('order')
      if (action) next.set('action', action)
      else next.delete('action')
      return next
    })
  }
  function done(message) { setNotice(message); list.refresh(); open(null) }
  const linkClass = 'cursor-pointer rounded-sm border-0 bg-transparent p-0 text-left text-[11px] font-semibold text-admin-blue hover:underline'
  const columns = [
    { key: 'OrderCode', label: 'Mã đơn', className: 'w-[10.1%]', render: (value) => <span className="font-semibold break-words text-admin-navy">{value}</span> },
    { key: 'ReceiverName', label: 'Khách hàng', className: 'w-[19.2%]', render: (value) => <span className="break-words">{value}</span> },
    { key: 'ReceiverPhone', label: 'SĐT', className: 'w-[11.9%]' },
    { key: 'OrderedAt', label: 'Ngày đặt', className: 'w-[12.4%]', render: formatDate },
    { key: 'OrderStatus', label: 'Trạng thái', className: 'w-[15.6%]', render: (value) => <OrderBadge value={value} /> },
    { key: 'next', label: 'Bước tiếp theo', className: 'w-[14.7%]', render: (_, row) => ORDER_NEXT[row.OrderStatus]
      ? canUpdate ? <button type="button" className={linkClass} aria-label={ORDER_NEXT[row.OrderStatus][1] + ' ' + row.OrderCode} onClick={() => open(row.OrderId, 'advance')}>{ORDER_NEXT[row.OrderStatus][1]}</button>
        : <span className="text-admin-muted">{ORDER_NEXT[row.OrderStatus][1]}</span>
      : <span className="text-admin-muted">{row.OrderStatus === 'Cancelled' ? 'Đã đóng' : 'Đã hoàn tất'}</span> },
    { key: 'actions', label: 'Thao tác', className: 'w-[16.1%]', render: (_, row) => <button type="button" className={linkClass} aria-label={'Xem chi tiết ' + row.OrderCode} onClick={() => navigate('/admin/orders/' + encodeURIComponent(row.OrderId) + orderListSearch(params))}>Xem chi tiết</button> },
  ]

  return <section className="flex min-w-0 flex-col gap-[18px]" aria-label="Quản lý đơn hàng">
    <div className="flex h-[46px] items-center"><h2 className="m-0 text-xl font-bold">Danh sách đơn hàng</h2></div>
    {notice && <div role="status" className="flex items-center justify-between gap-3 rounded-[10px] bg-green-50 p-3 text-xs text-green-700">{notice}<button type="button" aria-label="Đóng thông báo" className="cursor-pointer border-0 bg-transparent text-inherit" onClick={() => setNotice('')}>×</button></div>}
    <OrderSearch keyword={filter.keyword} onSearch={(value) => change('keyword', value)} />
    <div role="group" aria-label="Lọc trạng thái đơn hàng" className="flex min-h-10 flex-wrap items-center gap-2">
      {ORDER_STATUSES.map(([status, label, width]) => <button key={status} type="button" aria-pressed={filter.status === status} className={'h-9 cursor-pointer rounded-[9px] border border-admin-border bg-white text-[11px] font-semibold whitespace-nowrap text-admin-muted hover:bg-admin-soft aria-pressed:border-admin-blue aria-pressed:bg-admin-soft aria-pressed:text-admin-blue ' + width} onClick={() => change('status', status)}>{label}</button>)}
    </div>
    <div className="flex min-h-[560px] min-w-0 flex-col gap-3 rounded-[14px] border border-admin-border bg-white p-[18px]">
      <div className="flex min-h-9 items-center gap-2.5"><h3 className="m-0 text-[15px] font-semibold">Đơn hàng</h3>
        <span className="rounded-full bg-admin-soft px-[9px] py-[5px] text-[11px] font-semibold text-admin-blue">{list.loading ? 'Đang tải…' : list.error ? 'Chưa tải được' : total + ' đơn hàng'}</span>
        <span className="ml-auto text-right text-[11px] text-admin-muted">Có thể chọn một đơn để xem chi tiết hoặc cập nhật trạng thái</span>
      </div>
      <AdminTable variant="products" columns={columns} rows={rows} rowKey="OrderId" label="Danh sách đơn hàng" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText={filter.keyword || filter.status ? 'Không có đơn hàng phù hợp.' : 'Chưa có đơn hàng.'}
        className="min-w-[940px] table-fixed [&_th]:h-11! [&_th]:font-semibold! [&_td]:h-[78px]! [&_td]:py-2 [&_td]:break-words" />
      {!list.loading && !list.error && filter.page <= pages && <div className="mt-auto flex min-h-[42px] flex-col justify-center"><Pagination variant="admin" label="Phân trang đơn hàng" itemLabel="đơn hàng" page={filter.page} pageSize={ORDER_PAGE_SIZE} total={total} onPageChange={(value) => change('page', String(value))} /></div>}
    </div>
    {params.get('order') && <OrderDialog key={params.get('order') + '-' + (params.get('action') ?? '')} orderId={params.get('order')} initialAction={canUpdate && params.get('action') === 'advance' ? 'advance' : null} onClose={() => open(null)} onDone={done} />}
  </section>
}
