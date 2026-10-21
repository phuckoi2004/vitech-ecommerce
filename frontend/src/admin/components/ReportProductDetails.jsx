import { useEffect, useId, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Pagination } from '../../components/shared/index.js'
import { formatMoney } from '../../lib/format.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { REPORT_PAGE_SIZE, reportRangeLabel } from '../lib/reports.js'
import AdminTable from './AdminTable.jsx'

const money = (value) => value == null ? <span className="text-admin-muted">Chưa có giá nhập</span> : formatMoney(value)
export default function ReportProductDetails({ product, query, onClose }) {
  const location = useLocation()
  const dialog = useRef(null), title = useId(), [page, setPage] = useState(1)
  const state = useAdminQuery('/admin/statistics/reports/revenue/lines', { ...query, product_id: product.ProductId, page, page_size: REPORT_PAGE_SIZE })
  useEffect(() => { const element = dialog.current; element.showModal(); return () => element.close() }, [])
  const lastPage = Math.max(1, Math.ceil((state.data?.Total ?? 0) / REPORT_PAGE_SIZE))
  if (state.data && !state.loading && page > lastPage) setPage(lastPage)
  const columns = [
    { key: 'OrderCode', label: 'Mã đơn', render: (code, row) => <Link className="font-semibold text-admin-blue hover:underline" to={'/admin/orders/' + encodeURIComponent(row.OrderId)} state={{ reportOrigin: { search: location.search || '?' } }}>{code}</Link> },
    { key: 'DeliveredAt', label: 'Ngày giao', render: (date) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(date)) },
    { key: 'Sku', label: 'SKU / Biến thể', render: (sku, row) => <span>{sku}<small className="mt-1 block text-xs text-admin-muted">{row.VariantInfo}</small></span> },
    { key: 'Quantity', label: 'SL' }, { key: 'UnitPrice', label: 'Đơn giá', render: money },
    { key: 'Discount', label: 'Giảm giá', render: money }, { key: 'Revenue', label: 'Tiền hàng', render: money },
    { key: 'UnitCost', label: 'Giá nhập / SP', render: money }, { key: 'Cost', label: 'Tổng giá nhập', render: money },
    { key: 'Profit', label: 'Lãi gộp', render: money },
  ]
  return <dialog ref={dialog} className="report-drawer font-admin" aria-labelledby={title} onCancel={(event) => { event.preventDefault(); onClose() }} onClick={(event) => { if (event.target === dialog.current) onClose() }}>
    <div className="flex min-h-full flex-col gap-5"><header className="flex items-start justify-between gap-4"><div><h2 id={title} className="m-0 text-xl font-bold">{product.ProductName}</h2><p className="mt-2 mb-0 text-sm text-admin-muted">Các dòng đơn đã ghi nhận bán hàng · {reportRangeLabel(query.date_from, query.date_to)}</p></div><button type="button" autoFocus className="report-button" onClick={onClose}>Đóng</button></header>
      <p className="m-0 rounded-lg bg-admin-page p-3 text-sm text-admin-muted">Giá bán, giảm giá và giá nhập được lấy từ dữ liệu đã lưu trên đơn. Bấm mã đơn để xem chi tiết; nút Quay lại báo cáo sẽ giữ nguyên kỳ, bộ lọc và sản phẩm đang xem.</p>
      <AdminTable label="Chi tiết bán hàng theo đơn" columns={columns} rows={state.data?.Items ?? []} rowKey="Key" loading={state.loading} error={state.error} onRetry={state.refresh} emptyText="Chưa có dòng đơn trong kỳ đã chọn." className="report-table" />
      {state.data?.Total > REPORT_PAGE_SIZE && <Pagination variant="admin" itemLabel="dòng đơn" page={page} pageSize={REPORT_PAGE_SIZE} total={state.data.Total} onPageChange={setPage} />}
    </div>
  </dialog>
}
