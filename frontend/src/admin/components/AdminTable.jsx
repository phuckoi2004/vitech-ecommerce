import { EmptyState, ErrorState, LoadingState } from '../../components/shared/index.js'
import { formatDate, formatMoney } from '../../lib/format.js'

const ORDER_STATUS = {
  Pending: ['Chờ xử lý', 'bg-[#f59e0b] text-admin-text'],
  Confirmed: ['Đã xác nhận', 'bg-admin-soft text-admin-blue'],
  Processing: ['Đang xử lý', 'bg-admin-soft text-admin-blue'],
  Shipping: ['Đang giao', 'bg-admin-soft text-admin-blue'],
  Delivered: ['Đã giao', 'bg-[#16a34a] text-white'],
  Completed: ['Hoàn thành', 'bg-[#16a34a] text-white'],
  Cancelled: ['Đã hủy', 'bg-admin-red text-white'],
}

export function OrderStatus({ value }) {
  const [label, classes] = ORDER_STATUS[value] ?? [value, 'bg-admin-soft text-admin-blue']
  return <span className={`inline-block rounded-full px-2.5 py-1.5 text-[11px] font-semibold whitespace-nowrap ${classes}`}>{label}</span>
}

export const ORDER_COLUMNS = [
  { key: 'OrderCode', label: 'Mã đơn' },
  { key: 'ReceiverName', label: 'Người nhận' },
  { key: 'TotalAmount', label: 'Giá trị', render: formatMoney },
  { key: 'OrderStatus', label: 'Trạng thái', render: (value) => <OrderStatus value={value} /> },
  { key: 'OrderedAt', label: 'Ngày đặt', render: formatDate },
]

export default function AdminTable({ columns, rows = [], rowKey, loading, error, onRetry, emptyText = 'Chưa có dữ liệu.', emptyContent, label = 'Bảng dữ liệu', className = '', variant }) {
  const products = variant === 'products'
  return <div className="admin-table-region w-full rounded-sm" role="region" aria-label={label} aria-busy={loading}>
    <div className="admin-table-scroll w-full overflow-x-auto" tabIndex={0}><table className={`admin-table ${products ? 'admin-table--products' : ''} w-full border-collapse text-left text-sm leading-normal ${className}`}>
      <thead><tr>{columns.map((column) => <th key={column.key} scope="col" className={`border-b border-admin-border bg-admin-page px-3.5 py-3.5 text-[13px] font-semibold whitespace-nowrap text-admin-muted ${column.className ?? ''}`}>{column.label}</th>)}</tr></thead>
      <tbody>
        {!loading && !error && rows.map((row) => <tr key={row[rowKey]}>{columns.map((column) => <td key={column.key} className={`border-b border-admin-border px-3.5 py-4 text-sm align-middle ${column.className ?? ''}`}>{column.render ? column.render(row[column.key], row) : row[column.key] ?? '—'}</td>)}</tr>)}
      </tbody>
    </table></div>
    {(loading || error || !rows.length) && <div className="flex min-h-[170px] items-center justify-center">
      {loading ? <LoadingState label="Đang tải dữ liệu…" className="py-8" /> : error ? <ErrorState title="Không tải được dữ liệu" message={error} onRetry={onRetry} className="py-6" /> : emptyContent ?? <EmptyState title={emptyText} headingLevel={4} className="py-10 [&_h4]:text-xs [&_h4]:font-normal [&_h4]:text-admin-muted" />}
    </div>}
  </div>
}

export function AdminPanel({ title, action, children, className = '', ...props }) {
  return <section className={`admin-panel min-w-0 rounded-[16px] border border-admin-border bg-white p-[22px] ${className}`} {...props}>
    {title && <header className="mb-4 flex flex-wrap items-center justify-between gap-3"><h3 className="m-0 text-lg font-semibold">{title}</h3>{action}</header>}
    {children}
  </section>
}
