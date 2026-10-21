import { REPORT_TABS, reportRangeLabel } from '../lib/reports.js'
import ReportFilters from './ReportFilters.jsx'
import ReportChart from './ReportChart.jsx'
import ReportSummary from './ReportSummary.jsx'
import ReportTable from './ReportTable.jsx'
import ReportBreakdown from './ReportBreakdown.jsx'
import './Reports.css'

export default function ReportsWorkspace({ tab, tabs, filter, onTab, onApply, options, state, page, onPage, onProduct, onSort, onCancelled, cancelledOpen, onDelivered, deliveredOpen, children }) {
  const period = state.data?.Period
  return <section aria-label="Báo cáo thống kê" className="flex min-w-0 flex-col gap-5 font-admin text-admin-text">
    <header className="flex flex-wrap items-center justify-between gap-3"><h2 className="m-0 text-xl font-bold">{tab === 'orders' ? 'Thống kê đơn hàng' : 'Thống kê doanh thu'}</h2><button type="button" disabled={state.loading || options.loading} onClick={() => { state.refresh(); options.refresh() }} className="report-button">Làm mới</button></header>
    <nav aria-label="Loại báo cáo" className="flex w-fit max-w-full gap-1 rounded-xl border border-admin-border bg-white p-1">{tabs.map((id) => <button key={id} type="button" aria-current={tab === id ? 'page' : undefined} onClick={() => onTab(id)} className={'cursor-pointer rounded-lg border-0 px-5 py-2.5 text-sm ' + (tab === id ? 'bg-admin-blue font-semibold text-white' : 'bg-transparent font-medium text-admin-muted hover:bg-admin-soft')}>{REPORT_TABS[id]}</button>)}</nav>
    <ReportFilters key={JSON.stringify(filter)} value={filter} options={options.data ?? {}} loading={options.loading} error={options.error} onApply={onApply} />
    {options.error && <button type="button" onClick={options.refresh} className="w-fit cursor-pointer border-0 bg-transparent p-0 text-sm text-admin-blue underline">Thử lại danh sách bộ lọc</button>}
    {period && <div className="flex flex-wrap items-center justify-between gap-2 text-sm"><p className="m-0 font-medium">Đang xem: {reportRangeLabel(period.DateFrom, period.DateTo)} <span className="font-normal text-admin-muted">· Múi giờ GMT+7</span></p><span className="text-xs text-admin-muted">{tab === 'revenue' ? 'Ghi nhận theo ngày giao hàng' : 'Theo ngày đặt hàng'}</span></div>}
    <ReportSummary tab={tab} data={state.data?.Summary} loading={state.loading} error={state.error} filtered={!!(filter.product_id || filter.brand_id || filter.category_id)} onCancelled={onCancelled} cancelledOpen={cancelledOpen} onDelivered={onDelivered} deliveredOpen={deliveredOpen} />
    {children}
    <div className="grid min-w-0 grid-cols-[minmax(0,2fr)_minmax(260px,1fr)] gap-5 max-[1200px]:grid-cols-1"><ReportChart tab={tab} points={state.data?.Chart} loading={state.loading} error={state.error} onRetry={state.refresh} /><ReportBreakdown tab={tab} state={state} onProduct={onProduct} /></div>
    <ReportTable tab={tab} state={state} page={page} onPage={onPage} onProduct={onProduct} sort={filter.sort} onSort={onSort} />
    <details className="rounded-xl border border-admin-border bg-white px-5 py-4 text-sm"><summary className="cursor-pointer font-semibold">Cách tính</summary><div className="mt-3 space-y-2 text-admin-muted">{tab === 'revenue' ? <>
      <p><strong>Doanh số:</strong> Tổng tiền hàng sau tất cả giảm giá, không gồm phí vận chuyển. Chỉ tính đơn đã giao hoặc hoàn tất có giao dịch thanh toán thành công, theo ngày giao hàng.</p>
      <p><strong>Tổng giá nhập:</strong> Giá nhập đã lưu trên từng dòng đơn nhân với số lượng tương ứng, rồi cộng lại.</p>
      <p><strong>Lãi gộp:</strong> Doanh số − tổng giá nhập. Biên lãi (%) = (lãi gộp / doanh số) × 100.</p>
      <p><strong>Thiếu giá nhập:</strong> Nếu có dòng đơn chưa có giá nhập, tổng giá nhập và lãi gộp hiển thị “Chưa đủ dữ liệu”.</p>
      <p><strong>Phạm vi số liệu:</strong> Doanh số và lãi gộp chưa bao gồm các điều chỉnh do trả hàng. Tiền hoàn, khoản thu dư và phí vận chuyển được theo dõi riêng trong phần đối soát thanh toán. Mỗi đơn chỉ được đếm một lần trong phạm vi bộ lọc đang chọn.</p>
    </> : <>
      <p><strong>Số đơn hàng:</strong> Đếm các đơn được đặt trong khoảng thời gian đã chọn, theo trạng thái hiện tại.</p>
      <p><strong>Đã giao:</strong> Gồm đơn ở trạng thái “Đã giao” hoặc “Hoàn tất”, kể cả khi chưa thanh toán.</p>
      <p><strong>Tỷ lệ hủy:</strong> (Số đơn đã hủy / tổng số đơn đặt trong kỳ) × 100%.</p>
      <p><strong>Thời gian thống kê:</strong> Báo cáo đơn hàng tính theo ngày đặt, còn báo cáo bán hàng tính theo ngày giao. Vì vậy, số đơn trên hai báo cáo có thể khác nhau.</p>
      <p><strong>Lý do hủy:</strong> Hiển thị nội dung đã được ghi khi hủy đơn. Các nội dung giống nhau được gộp lại để đếm số lần xuất hiện.</p>
    </>}</div></details>
  </section>
}
