import { Pagination } from '../../components/shared/index.js'
import { formatMoney } from '../../lib/format.js'
import { REPORT_PAGE_SIZE, reportColumns, reportMargin } from '../lib/reports.js'
import AdminTable from './AdminTable.jsx'

const amount = (value) => value == null ? <span className="text-admin-muted" title="Có dòng chưa có giá nhập">—</span> : formatMoney(value)
export default function ReportTable({ tab, state, page, onPage, onProduct, sort = 'revenue_desc', onSort }) {
  const sales = tab === 'revenue'
  const columns = reportColumns(tab).map(([key, label]) => ({ key, label,
    ...(key === 'ProductName' ? { className: 'min-w-[240px]', render: (name, row) => <div><button type="button" className="cursor-pointer border-0 bg-transparent p-0 text-left font-semibold text-admin-blue hover:underline" onClick={() => onProduct(row)}>{name}{row.ProductVariantId && <span className="mt-1 block text-xs font-medium">{row.VariantName} · {row.Sku}</span>}</button><small className="mt-1 block text-xs text-admin-muted">{row.CategoryName} · {row.BrandName}</small></div> } : {}),
    ...(['Revenue', 'Cost', 'Profit'].includes(key) ? { render: (value) => <span className={key === 'Profit' && Number(value) < 0 ? 'text-admin-red' : undefined}>{amount(value)}</span> } : {}),
    ...(key === 'Margin' ? { render: reportMargin } : {}),
    ...(['ReceivedQuantity', 'Quantity', 'StockQuantity'].includes(key) ? { render: (value) => value == null ? '—' : Number(value).toLocaleString('vi-VN') } : {}),
  }))
  return <section aria-label={sales ? 'Kết quả theo sản phẩm' : 'Đơn đặt theo tháng'} className="overflow-hidden rounded-[14px] border border-admin-border bg-white">
    <header className="flex flex-wrap items-center justify-between gap-3 p-5"><div><h3 className="m-0 text-base font-semibold">{sales ? 'Kết quả theo sản phẩm' : 'Đơn đặt theo tháng'}</h3><p className="mt-1 mb-0 text-xs text-admin-muted">{sales ? 'Mỗi dòng một màu/biến thể · Bấm sản phẩm để xem từng dòng đơn' : 'Trạng thái hiện tại của các đơn đặt trong từng tháng'}</p></div>
      {sales && <label className="flex items-center gap-2 text-xs text-admin-muted">Sắp xếp<select aria-label="Sắp xếp sản phẩm" className="rounded-lg border border-admin-border bg-white px-2 text-sm text-admin-text" value={sort} onChange={(e) => onSort(e.target.value)}>{[['revenue_desc','Doanh số giảm dần'],['revenue_asc','Doanh số tăng dần'],['quantity_desc','SL bán giảm dần'],['quantity_asc','SL bán tăng dần'],['cost_desc','Giá nhập giảm dần'],['cost_asc','Giá nhập tăng dần'],['profit_desc','Lãi gộp giảm dần'],['profit_asc','Lãi gộp tăng dần'],['margin_desc','Biên lãi giảm dần'],['margin_asc','Biên lãi tăng dần'],['name_asc','Tên A–Z'],['name_desc','Tên Z–A']].map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>}
    </header>
    {sales && <p className="mx-5 mt-0 mb-4 text-xs text-admin-muted">Theo đúng màu/biến thể trên từng dòng. SL nhập: tồn khai báo ban đầu + hàng thực nhận trong kỳ · SL bán: hàng ghi nhận bán trong kỳ · SL còn: tồn hiện tại.</p>}
    <AdminTable label={sales ? 'Kết quả theo sản phẩm' : 'Đơn đặt theo tháng'} columns={columns} rows={state.data?.Items ?? []} rowKey="Key" loading={state.loading} error={state.error} onRetry={state.refresh} emptyText="Chưa có dữ liệu trong kỳ đã chọn." className="report-table" />
    {!state.loading && !state.error && state.data && <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-admin-border p-4 text-xs text-admin-muted"><span>{sales ? 'Tổng toàn kỳ: ' + formatMoney(state.data.Summary.Revenue) + ' · ' + (state.data.Summary.Quantity ?? 0).toLocaleString('vi-VN') + ' sản phẩm bán' : 'Tổng ' + state.data.Summary.TotalOrders + ' đơn đặt'}</span>{state.data.Total > REPORT_PAGE_SIZE && <Pagination variant="admin" itemLabel={sales ? 'biến thể' : 'tháng'} page={page} pageSize={REPORT_PAGE_SIZE} total={state.data.Total} onPageChange={onPage} />}</footer>}
  </section>
}
