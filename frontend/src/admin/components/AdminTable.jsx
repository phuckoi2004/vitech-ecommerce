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

export default function AdminTable({ columns, rows = [], rowKey, loading, error, onRetry, emptyText = 'Chưa có dữ liệu.', label = 'Bảng dữ liệu', className = '', variant }) {
  const products = variant === 'products'
  return <div className="w-full rounded-sm" role="region" aria-label={label} aria-busy={loading}>
    <div className="w-full overflow-x-auto" tabIndex={0}><table className={`w-full border-collapse text-left text-xs leading-normal ${className}`}>
      <thead><tr>{columns.map((column) => <th key={column.key} scope="col" className={`h-11 py-2.5 text-[11px] font-medium whitespace-nowrap text-admin-muted ${products ? 'bg-admin-page px-2.5 first:rounded-l-[9px] last:rounded-r-[9px]' : 'border-b border-admin-border pr-3 last:pr-0'} ${column.className ?? ''}`}>{column.label}</th>)}</tr></thead>
      <tbody>
        {!loading && !error && rows.map((row) => <tr key={row[rowKey]}>{columns.map((column) => <td key={column.key} className={`${products ? 'h-[76px] px-2.5 text-[11px]' : 'h-11 border-b border-admin-border py-2.5 pr-3 last:pr-0'} align-middle ${column.className ?? ''}`}>{column.render ? column.render(row[column.key], row) : row[column.key] ?? '—'}</td>)}</tr>)}
      </tbody>
    </table></div>
    {(loading || error || !rows.length) && <div className="flex min-h-[170px] items-center justify-center">
      {loading ? <LoadingState label="Đang tải dữ liệu…" className="py-8" /> : error ? <ErrorState title="Không tải được dữ liệu" message={error} onRetry={onRetry} className="py-6" /> : <EmptyState title={emptyText} headingLevel={4} className="py-10 [&_h4]:text-xs [&_h4]:font-normal [&_h4]:text-admin-muted" />}
    </div>}
  </div>
}

export function AdminPanel({ title, action, children, className = '', ...props }) {
  return <section className={`min-w-0 rounded-[14px] border border-admin-border bg-white p-[18px] ${className}`} {...props}>
    {title && <header className="mb-[13px] flex items-center justify-between gap-3"><h3 className="m-0 text-[15px] font-semibold">{title}</h3>{action}</header>}
    {children}
  </section>
}
