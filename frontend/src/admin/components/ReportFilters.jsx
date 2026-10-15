import { useState } from 'react'
import { defaultReportFilters, reportPeriods } from '../lib/reports.js'

const control = 'h-[38px] w-full min-w-0 rounded-lg border border-admin-border bg-white px-2.5 text-[9px] font-normal text-admin-text disabled:opacity-50'
export default function ReportFilters({ value, options = {}, loading, error, onApply }) {
  const [draft, setDraft] = useState(value)
  const change = (key, next) => setDraft((previous) => ({ ...previous, [key]: next, ...(['category_id', 'brand_id'].includes(key) ? { product_id: '' } : {}) }))
  const fields = [
    ['category_id', 'Danh mục', 'Categories'], ['brand_id', 'Thương hiệu', 'Brands'], ['product_id', 'Sản phẩm', 'Products'],
  ]
  return <form role="search" aria-label="Bộ lọc báo cáo" onSubmit={(event) => { event.preventDefault(); onApply(draft) }} className="rounded-xl border border-admin-border bg-white p-3">
    <div className="flex items-end gap-2">
      <label className="flex min-w-0 flex-1 flex-col gap-[5px] text-[9px] font-medium text-admin-muted">Thời gian<select className={control} value={draft.period} onChange={(event) => change('period', event.target.value)}>{reportPeriods().map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      {fields.map(([key, label, source]) => <label key={key} className="flex min-w-0 flex-1 flex-col gap-[5px] text-[9px] font-medium text-admin-muted">{label}<select className={control} value={draft[key]} disabled={loading || !!error} onChange={(event) => change(key, event.target.value)}><option value="">Tất cả</option>{(options?.[source] ?? []).filter((item) => source !== 'Products' || ((!draft.category_id || item.CategoryId === draft.category_id) && (!draft.brand_id || item.BrandId === draft.brand_id))).map((item) => <option key={item.Id} value={item.Id}>{item.Name}</option>)}</select></label>)}
      <div className="ml-auto flex shrink-0 gap-2 pl-2"><button type="button" className="h-8 cursor-pointer rounded-[9px] border border-admin-border bg-white px-[13px] text-[10px] font-semibold hover:bg-admin-page" onClick={() => { const empty = defaultReportFilters(); setDraft(empty); onApply(empty) }}>Xóa lọc</button><button type="submit" className="h-8 cursor-pointer rounded-[9px] border border-admin-blue bg-admin-blue px-[13px] text-[10px] font-semibold text-white hover:bg-admin-navy">Áp dụng</button></div>
    </div>
    {error && <p role="alert" className="mt-2 mb-0 text-[10px] text-admin-red">Không tải được danh sách bộ lọc: {error}</p>}
  </form>
}
