import { Pagination } from '../../components/shared/index.js'
import { formatMoney } from '../../lib/format.js'
import { REPORT_PAGE_SIZE, reportColumns } from '../lib/reports.js'
import AdminTable from './AdminTable.jsx'

export default function ReportTable({ tab, state, page, onPage }) {
  const columns = reportColumns(tab).map(([key, label], index) => ({ key, label, className: tab === 'revenue' ? ['w-[16%]', 'w-[28%]', 'w-[17%]', 'w-[17%]', 'w-[22%]'][index] : ['w-[19%]', 'w-[17%]', 'w-[19%]', 'w-[17%]', 'w-[28%]'][index], ...(key === 'Revenue' ? { render: formatMoney } : {}) }))
  const title = tab === 'revenue' ? 'Chi tiết doanh thu' : 'Chi tiết số lượng đơn hàng'
  return <section aria-label={title} className="min-h-[238px] overflow-hidden rounded-xl border border-admin-border bg-white">
    <header className="flex min-h-[54px] items-center px-[13px] py-2.5"><h3 className="m-0 text-xs leading-normal font-semibold">{title}</h3></header>
    <AdminTable label={title} columns={columns} rows={state.data?.Items ?? []} rowKey="Key" loading={state.loading} error={state.error} onRetry={state.refresh} emptyText="Chưa có dữ liệu trong kỳ đã chọn." className="table-fixed [&_th]:h-[43px]! [&_th]:border-b-0! [&_th]:px-2! [&_th]:text-[8px]! [&_th]:font-semibold! [&_td]:h-[43px]! [&_td]:px-2! [&_td]:text-[9px]! [&_td]:break-words" />
    {!state.loading && !state.error && state.data?.Total > REPORT_PAGE_SIZE && <div className="px-[13px] py-3"><Pagination variant="admin" itemLabel="dòng" page={page} pageSize={REPORT_PAGE_SIZE} total={state.data.Total} onPageChange={onPage} /></div>}
  </section>
}
