import { REPORT_TABS, reportRangeLabel } from '../lib/reports.js'
import ReportFilters from './ReportFilters.jsx'
import ReportChart from './ReportChart.jsx'
import ReportSummary from './ReportSummary.jsx'
import ReportTable from './ReportTable.jsx'

export default function ReportsWorkspace({ tab, tabs, filter, onTab, onApply, options, state, page, onPage }) {
  return <section aria-label="Báo cáo thống kê" className="-mx-1 -my-2 flex min-w-0 flex-col gap-3 font-admin text-admin-text">
    <header className="flex min-h-[38px] items-center justify-between gap-4"><div><h2 className="m-0 text-lg leading-normal font-bold">{REPORT_TABS[tab]}</h2>{tab === 'revenue' && <p className="mt-0.5 mb-0 text-[10px] leading-normal text-admin-muted">Theo dõi doanh thu theo thời gian và các tiêu chí kinh doanh</p>}</div><button type="button" disabled={state.loading || options.loading} onClick={() => { state.refresh(); options.refresh() }} className="h-8 cursor-pointer rounded-[9px] border border-admin-border bg-white px-[13px] text-[10px] font-semibold hover:bg-admin-page disabled:cursor-progress disabled:opacity-50">Làm mới</button></header>
    <nav aria-label="Loại báo cáo" className="flex w-fit gap-0.5 rounded-[10px] bg-admin-page p-1">{tabs.map((id) => <button key={id} type="button" aria-current={tab === id ? 'page' : undefined} onClick={() => onTab(id)} className={'cursor-pointer rounded-lg border-0 px-4 py-2.5 text-[10px] leading-normal ' + (tab === id ? 'bg-admin-blue font-semibold text-white' : 'bg-transparent font-medium text-admin-muted hover:bg-admin-soft')}>{REPORT_TABS[id]}</button>)}</nav>
    <ReportFilters key={tab + JSON.stringify(filter)} tab={tab} value={filter} options={options.data} loading={options.loading} error={options.error} onApply={onApply} />
    {options.error && <button type="button" onClick={options.refresh} className="w-fit cursor-pointer border-0 bg-transparent p-0 text-[10px] text-admin-blue underline">Thử lại danh sách bộ lọc</button>}
    <ReportSummary tab={tab} data={state.data?.Summary} loading={state.loading} error={state.error} />
    <ReportChart tab={tab} points={state.data?.Chart} loading={state.loading} error={state.error} />
    <ReportTable tab={tab} state={state} page={page} onPage={onPage} />
    {state.data?.Period && <p className="m-0 text-[9px] text-admin-muted">Kỳ báo cáo: {reportRangeLabel(state.data.Period.DateFrom, state.data.Period.DateTo)}. {tab === 'revenue' ? 'Doanh số sản phẩm sau giảm giá, thuộc đơn đã giao và đã xác nhận thanh toán, theo ngày giao hàng; không gồm phí vận chuyển và chưa trừ hoàn tiền.' : 'Đơn hàng theo ngày đặt. Giao thành công gồm đơn đã giao và đã hoàn thành.'}</p>}
  </section>
}
