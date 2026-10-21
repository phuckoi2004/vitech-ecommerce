import { useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Pagination } from '../../components/shared/index.js'
import { formatDateTime, formatMoney } from '../../lib/format.js'
import { formatStatus } from '../../lib/status-labels.js'
import { REPORT_PAGE_SIZE, reportRangeLabel } from '../lib/reports.js'
import AdminTable from './AdminTable.jsx'

export default function ReportOrderDetails({ kind, state, query, page, onPage, onClose, canViewOrders }) {
  const location = useLocation(), section = useRef(null)
  useEffect(() => { section.current?.focus() }, [])
  const delivered = kind === 'delivered', label = delivered ? 'đã giao' : 'đã hủy'
  const columns = [
    { key: 'OrderCode', label: 'Mã đơn', className: 'w-[160px] whitespace-nowrap', render: (code, row) => canViewOrders
      ? <Link className="font-semibold text-admin-blue hover:underline" to={'/admin/orders/' + encodeURIComponent(row.OrderId)} state={{ reportOrigin: { search: location.search || '?' } }}>{code}</Link> : code },
    { key: 'OrderedAt', label: 'Ngày đặt', className: 'w-[160px]', render: formatDateTime },
    ...(delivered ? [{ key: 'DeliveredAt', label: 'Ngày giao', className: 'w-[160px]', render: formatDateTime }] : []),
    { key: 'CustomerName', label: 'Khách hàng', className: 'w-[180px]' },
    { key: 'TotalAmount', label: 'Giá trị đơn', className: 'w-[150px] text-right tabular-nums', render: formatMoney },
    delivered ? { key: 'OrderStatus', label: 'Trạng thái', render: (status) => formatStatus(status) }
      : { key: 'CancelReason', label: 'Lý do hủy', render: (reason) => <span className="whitespace-pre-wrap">{reason?.trim() || 'Không ghi lý do'}</span> },
  ]
  return <section ref={section} id={'report-' + kind + '-orders'} tabIndex={-1} aria-labelledby={'report-' + kind + '-heading'} className="min-w-0 scroll-mt-24 overflow-hidden rounded-[14px] border border-admin-border bg-white">
    <header className="flex flex-wrap items-start justify-between gap-3 p-5"><div><h3 id={'report-' + kind + '-heading'} className="m-0 text-base font-semibold">Đơn {label} trong kỳ</h3><p className="mt-1 mb-0 text-xs text-admin-muted">{reportRangeLabel(query.date_from, query.date_to)} · Múi giờ GMT+7</p><p className="mt-1 mb-0 text-xs text-admin-muted">{delivered ? 'Đơn đặt trong kỳ, hiện đã giao hoặc hoàn tất, kể cả khi chưa thanh toán.' : 'Đơn đặt trong kỳ và hiện đã hủy.'} Giá trị đơn gồm phí vận chuyển, nếu có.</p></div><button type="button" className="report-button" onClick={onClose}>Đóng danh sách</button></header>
    <AdminTable label={'Danh sách đơn ' + label} columns={columns} rows={state.data?.Items ?? []} rowKey="OrderId" loading={state.loading} error={state.error} onRetry={state.refresh} emptyText={'Không có đơn ' + label + ' trong kỳ theo bộ lọc đang chọn.'} className={'report-' + kind + '-table [&_td]:align-top'} />
    {!state.loading && !state.error && state.data && <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-admin-border p-4 text-xs text-admin-muted"><span>{state.data.Total.toLocaleString('vi-VN')} đơn {label}</span>{state.data.Total > REPORT_PAGE_SIZE && <Pagination variant="admin" label={'Phân trang đơn ' + label} itemLabel="đơn" page={page} pageSize={REPORT_PAGE_SIZE} total={state.data.Total} onPageChange={onPage} />}</footer>}
  </section>
}
