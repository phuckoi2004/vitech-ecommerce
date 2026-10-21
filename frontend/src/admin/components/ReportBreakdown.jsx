import { LoadingState } from '../../components/shared/index.js'
import { formatMoney } from '../../lib/format.js'
import { reportRate } from '../lib/reports.js'

export default function ReportBreakdown({ tab, state, onProduct }) {
  const sales = tab === 'revenue', items = sales ? state.data?.TopProducts ?? [] : state.data?.CancellationReasons ?? []
  const total = sales ? Number(state.data?.Summary.Revenue) : state.data?.Summary.CancelledOrders
  return <section aria-label={sales ? 'Top sản phẩm' : 'Lý do hủy đã ghi'} className="min-w-0 rounded-[14px] border border-admin-border bg-white p-5">
    <h3 className="m-0 text-base font-semibold">{sales ? 'Top 5 sản phẩm' : 'Lý do hủy đã ghi'}</h3>
    <p className="mt-1 mb-4 text-xs text-admin-muted">{sales ? 'Theo doanh số toàn kỳ' : 'Tối đa 10 nội dung phổ biến · Theo ngày đặt'}</p>
    {state.loading ? <LoadingState label="Đang tải phân tích…" /> : state.error ? <p className="text-sm text-admin-muted">Chưa tải được dữ liệu.</p> : !items.length ? <p className="py-10 text-center text-sm text-admin-muted">Chưa có dữ liệu trong kỳ đã chọn.</p> : <ol className="m-0 flex list-none flex-col gap-4 p-0">{items.map((row, index) => {
      const value = sales ? Number(row.Revenue) : row.TotalOrders
      return <li key={row.Key ?? row.Reason} className="min-w-0 text-sm"><div className="mb-1.5 flex items-start justify-between gap-3">{sales ? <button type="button" onClick={() => onProduct(row)} className="min-w-0 cursor-pointer border-0 bg-transparent p-0 text-left font-medium text-admin-blue hover:underline">{index + 1}. {row.ProductName}</button> : <span className="break-words">{row.Reason}</span>}<span className="shrink-0 text-xs tabular-nums">{sales ? formatMoney(row.Revenue) : value + ' đơn'}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-admin-page"><div className="h-full rounded-full" style={{ width: (total > 0 ? Math.min(100, value / total * 100) : 0) + '%', backgroundColor: sales ? '#1677ff' : '#e11d2e' }} /></div><p className="mt-1 mb-0 text-right text-xs text-admin-muted">{reportRate(value, total ?? 0)} {sales ? 'doanh số' : 'đơn hủy'}</p></li>
    })}</ol>}
  </section>
}
