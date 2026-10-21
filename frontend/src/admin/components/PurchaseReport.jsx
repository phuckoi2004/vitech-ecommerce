import { Link, useLocation } from 'react-router-dom'
import { LoadingState, Pagination } from '../../components/shared/index.js'
import { formatDateTime, formatMoney } from '../../lib/format.js'
import { REPORT_PAGE_SIZE, reportRate } from '../lib/reports.js'
import AdminTable from './AdminTable.jsx'
import { PurchaseStatus } from './PurchaseUi.jsx'
import ReportMetric from './ReportMetric.jsx'

const count = (value) => (value ?? 0).toLocaleString('vi-VN')
export function PurchaseReportSummary({ data, loading, error }) {
  const cards = [
    ['Phiếu nhập trong kỳ', count(data?.TotalOrders), 'Theo ngày tạo phiếu'],
    ['Đang xử lý', count(data?.InProgressOrders), 'Chờ xác nhận, đã xác nhận hoặc đang nhận'],
    ['Đã nhận đủ', count(data?.CompletedOrders), reportRate(data?.CompletedOrders ?? 0, data?.TotalOrders ?? 0) + ' số phiếu trong kỳ'],
    ['Đóng phiếu thiếu', count(data?.ClosedOrders), 'Đã đóng khi chưa nhận đủ hàng'],
    ['Hủy / từ chối', count((data?.CancelledOrders ?? 0) + (data?.RejectedOrders ?? 0)), count(data?.CancelledOrders) + ' hủy · ' + count(data?.RejectedOrders) + ' từ chối'],
    ['Số lượng đặt', count(data?.OrderedQuantity), 'Không gồm phiếu hủy / từ chối'],
    ['Số lượng đã nhận', count(data?.ReceivedQuantity), 'Lũy kế của các phiếu tạo trong kỳ'],
    ['Giá trị đặt hàng', formatMoney(data?.OrderedAmount ?? 0), 'Theo dòng hàng · Không gồm hủy / từ chối', data?.OrderedAmount],
  ]
  return <div aria-label="Tổng hợp báo cáo nhập hàng" aria-busy={loading} className="report-metrics grid grid-cols-4 gap-4 max-[1200px]:grid-cols-2">{cards.map(([label, value, note, money]) => <article key={label} aria-label={label} className="report-metric-card flex min-h-[142px] min-w-0 flex-col gap-2 rounded-[14px] border border-admin-border bg-white p-5">
    <h3 className="m-0 text-sm font-medium text-admin-muted">{label}</h3><p className="report-metric-value m-0 text-[26px] leading-tight font-bold tabular-nums wrap-anywhere">{loading || error ? '—' : <ReportMetric value={value} money={money} />}</p><p className="mt-auto mb-0 text-xs text-admin-muted">{note}</p>
  </article>)}</div>
}

export function PurchaseReportBreakdown({ state }) {
  const items = state.data?.Suppliers ?? [], total = Number(state.data?.Summary.OrderedAmount ?? 0)
  return <section aria-label="Top nhà cung cấp" className="min-w-0 rounded-[14px] border border-admin-border bg-white p-5">
    <h3 className="m-0 text-base font-semibold">Top 5 nhà cung cấp</h3><p className="mt-1 mb-4 text-xs text-admin-muted">Theo giá trị đặt hàng toàn kỳ · Bỏ phiếu hủy / từ chối khi tính giá trị</p>
    {state.loading ? <LoadingState label="Đang tải nhà cung cấp…" /> : state.error ? <p className="text-sm text-admin-muted">Chưa tải được dữ liệu.</p> : !items.length ? <p className="py-10 text-center text-sm text-admin-muted">Chưa có dữ liệu trong kỳ đã chọn.</p> : <ol className="m-0 flex list-none flex-col gap-4 p-0">{items.map((row, index) => <li key={row.SupplierId} className="min-w-0 text-sm">
      <div className="mb-1.5 flex flex-wrap justify-between gap-2"><span className="min-w-0 break-words font-medium">{index + 1}. {row.SupplierName}</span><span className="text-xs tabular-nums">{formatMoney(row.OrderedAmount)}</span></div>
      <div className="h-1.5 overflow-hidden rounded-full bg-admin-page"><div className="h-full rounded-full bg-admin-blue" style={{ width: (total > 0 ? Math.min(100, Number(row.OrderedAmount) / total * 100) : 0) + '%' }} /></div>
      <p className="mt-1 mb-0 text-xs text-admin-muted">{count(row.TotalOrders)} phiếu · {reportRate(Number(row.OrderedAmount), total)} giá trị đặt</p>
    </li>)}</ol>}
  </section>
}

export function PurchaseReportTable({ state, page, onPage, canViewPurchases }) {
  const location = useLocation()
  const columns = [
    { key: 'PurchaseOrderCode', label: 'Mã phiếu', className: 'whitespace-nowrap', render: (code, row) => canViewPurchases ? <Link className="font-semibold text-admin-blue hover:underline" to={'/admin/purchases/' + encodeURIComponent(row.PurchaseOrderId)} state={{ reportOrigin: { search: location.search || '?' } }}>{code}</Link> : code },
    { key: 'CreatedAt', label: 'Ngày tạo', render: formatDateTime },
    { key: 'SupplierName', label: 'Nhà cung cấp', className: 'min-w-[180px]' },
    { key: 'Status', label: 'Trạng thái', render: (value) => <PurchaseStatus status={value} /> },
    { key: 'OrderedQuantity', label: 'SL đặt', className: 'text-right tabular-nums', render: count },
    { key: 'ReceivedQuantity', label: 'SL đã nhận', className: 'text-right tabular-nums', render: count },
    { key: 'OrderedAmount', label: 'Giá trị đặt', className: 'text-right whitespace-nowrap tabular-nums', render: formatMoney },
  ]
  return <section aria-label="Danh sách phiếu nhập trong kỳ" className="min-w-0 overflow-hidden rounded-[14px] border border-admin-border bg-white">
    <header className="p-5"><h3 className="m-0 text-base font-semibold">Phiếu nhập trong kỳ</h3><p className="mt-1 mb-0 text-xs text-admin-muted">Mới nhất trước · Số lượng và giá trị theo sản phẩm đang lọc. Phiếu hủy / từ chối giữ giá trị đặt để tra cứu.</p></header>
    <AdminTable label="Phiếu nhập trong kỳ" columns={columns} rows={state.data?.Items ?? []} rowKey="PurchaseOrderId" loading={state.loading} error={state.error} onRetry={state.refresh} emptyText="Chưa có phiếu nhập trong kỳ theo bộ lọc đang chọn." className="report-purchases-table" />
    {!state.loading && !state.error && state.data && <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-admin-border p-4 text-xs text-admin-muted"><span>Tổng {count(state.data.Total)} phiếu nhập</span>{state.data.Total > REPORT_PAGE_SIZE && <Pagination variant="admin" label="Phân trang phiếu nhập" itemLabel="phiếu" page={page} pageSize={REPORT_PAGE_SIZE} total={state.data.Total} onPageChange={onPage} />}</footer>}
  </section>
}

export function PurchaseReportRules() {
  return <>
    <p><strong>Số phiếu nhập:</strong> Mỗi phiếu tạo trong kỳ được đếm một lần, theo ngày Việt Nam và trạng thái hiện tại.</p>
    <p><strong>Số lượng và giá trị đặt:</strong> Cộng các dòng hàng phù hợp bộ lọc, không gồm phiếu đã hủy hoặc bị từ chối. Giá trị đặt là số tiền trên phiếu, chưa thể hiện khoản tiền đã thanh toán cho nhà cung cấp.</p>
    <p><strong>Số lượng đã nhận:</strong> Lũy kế thực nhận đến thời điểm xem của các phiếu tạo trong kỳ, kể cả nhận sau kỳ. Đây không phải số lượng nhận riêng trong khoảng ngày đang chọn.</p>
    <p><strong>Bộ lọc:</strong> Nhà cung cấp, danh mục, thương hiệu và sản phẩm được kết hợp đồng thời. Khi lọc sản phẩm, chỉ tính các dòng hàng phù hợp; số phiếu và trạng thái vẫn đếm một lần mỗi phiếu.</p>
  </>
}
