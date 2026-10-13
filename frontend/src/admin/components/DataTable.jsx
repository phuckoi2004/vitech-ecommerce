export function formatMoney(value) {
  return `${Number(value ?? 0).toLocaleString('vi-VN')} ₫`
}

export function formatDate(value) {
  return value ? new Date(value).toLocaleDateString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric' }) : '—'
}

const ORDER_STATUSES = {
  Pending: ['Chờ xử lý', 'warning'], Confirmed: ['Đã xác nhận', 'neutral'], Processing: ['Đang xử lý', 'neutral'],
  Shipping: ['Đang giao', 'neutral'], Delivered: ['Đã giao', 'success'], Completed: ['Hoàn thành', 'success'], Cancelled: ['Đã hủy', 'danger'],
}

export function OrderStatus({ value }) {
  const [label, tone] = ORDER_STATUSES[value] ?? [value, 'neutral']
  const tones = {
    warning: 'bg-[#f59e0b] text-admin-text',
    neutral: 'bg-admin-soft-blue text-admin-blue',
    success: 'bg-[#16a34a] text-white',
    danger: 'bg-admin-red text-white',
  }
  return <span className={`inline-block rounded-full px-2.5 py-1.5 text-[11px] font-semibold whitespace-nowrap ${tones[tone]}`}>{label}</span>
}

export function DataError({ message, onRetry }) {
  if (!message) return null
  return <div className="flex items-center justify-between gap-3 rounded-[10px] border border-[#f5dcdf] bg-[#fff4f4] px-4 py-3 text-[13px] text-[#b9313b]" role="alert"><span>{message}</span><button type="button" className="shrink-0 cursor-pointer border-0 bg-transparent text-inherit underline" onClick={onRetry}>Thử lại</button></div>
}

export default function DataTable({ columns, rows = [], rowKey, loading = false, error = '', emptyText = 'Chưa có dữ liệu.', className = '' }) {
  return <div className="w-full overflow-x-auto rounded-[3px]" tabIndex={0} role="region" aria-label="Bảng dữ liệu" aria-busy={loading}>
    <table className={`w-full border-collapse text-left text-xs leading-normal ${className}`}>
      <thead><tr>{columns.map((column) => <th key={column.key} className="h-[42px] border-b border-admin-border py-2.5 pr-3 pl-0 text-[11px] font-medium whitespace-nowrap text-admin-muted last:pr-0" scope="col">{column.label}</th>)}</tr></thead>
      <tbody>
        {!loading && !error && rows.map((row) => <tr key={row[rowKey]}>{columns.map((column) => <td key={column.key} className="h-11 border-b border-admin-border py-2.5 pr-3 pl-0 align-middle last:pr-0">{column.render ? column.render(row[column.key], row) : row[column.key] ?? '—'}</td>)}</tr>)}
        {(loading || error || rows.length === 0) && <tr><td colSpan={columns.length} className="h-[170px] border-0 px-3 py-6 text-center align-middle text-admin-muted" role="status">{loading ? 'Đang tải dữ liệu…' : error ? 'Không tải được dữ liệu.' : emptyText}</td></tr>}
      </tbody>
    </table>
  </div>
}

export const ORDER_COLUMNS = [
  { key: 'OrderCode', label: 'Mã đơn' },
  // The order API exposes the recipient's name, not the customer's account name.
  { key: 'ReceiverName', label: 'Người nhận' },
  { key: 'TotalAmount', label: 'Giá trị', render: formatMoney },
  { key: 'OrderStatus', label: 'Trạng thái', render: (value) => <OrderStatus value={value} /> },
  { key: 'OrderedAt', label: 'Ngày đặt', render: formatDate },
]
