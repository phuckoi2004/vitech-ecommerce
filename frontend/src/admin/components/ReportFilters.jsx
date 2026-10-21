import { useId, useState } from 'react'
import { defaultReportFilters, reportPeriod, reportPeriods } from '../lib/reports.js'

const control = 'h-[42px] w-full min-w-0 rounded-lg border border-admin-border bg-white px-3 text-sm text-admin-text disabled:opacity-50'
export default function ReportFilters({ value, options = {}, loading, error, onApply }) {
  const [draft, setDraft] = useState(value), [validation, setValidation] = useState('')
  const [mobileOpen, setMobileOpen] = useState(false), fieldsId = useId()
  const active = ['category_id', 'brand_id', 'product_id'].filter((key) => value[key]).length
  const change = (key, next) => { setValidation(''); setDraft((previous) => ({ ...previous, [key]: next, ...(['category_id', 'brand_id'].includes(key) ? { product_id: '' } : {}) })) }
  const field = 'flex min-w-0 flex-col gap-1.5 text-[13px] font-medium text-admin-muted'
  function submit(event) {
    event.preventDefault()
    try { reportPeriod(draft); setValidation(''); onApply(draft) } catch (failure) { setValidation(failure.message) }
  }
  return <form role="search" aria-label="Bộ lọc báo cáo" onSubmit={submit} className="rounded-[14px] border border-admin-border bg-white p-4">
    <button type="button" className="report-filter-toggle" aria-expanded={mobileOpen} aria-controls={fieldsId} onClick={() => setMobileOpen((open) => !open)}>Bộ lọc báo cáo{active > 0 ? ' · ' + active + ' tiêu chí' : ''}<span aria-hidden="true">{mobileOpen ? '−' : '+'}</span></button>
    <div id={fieldsId} className="report-filter-fields" data-open={mobileOpen}>
    <div className="flex flex-wrap items-end gap-3 [&_label]:min-w-[170px] [&_label]:flex-1 max-[600px]:[&_label]:basis-full">
      <label className={field}>Kỳ báo cáo<select className={control} value={draft.period} onChange={(event) => change('period', event.target.value)}>{reportPeriods().map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      {draft.period === 'month' && <label className={field}>Tháng<input className={control} type="month" required min="1900-01" max="9998-12" value={draft.month} onChange={(event) => change('month', event.target.value)} /></label>}
      {['quarter', 'year'].includes(draft.period) && <label className={field}>Năm<input className={control} type="number" required min="1900" max="9998" value={draft.year} onChange={(event) => change('year', event.target.value)} /></label>}
      {draft.period === 'quarter' && <label className={field}>Quý<select className={control} value={draft.quarter} onChange={(event) => change('quarter', event.target.value)}>{[1, 2, 3, 4].map((q) => <option key={q} value={q}>Quý {q}</option>)}</select></label>}
      {draft.period === 'custom' && <>{[['date_from', 'Từ ngày'], ['date_to', 'Đến ngày']].map(([key, label]) => <label key={key} className={field}>{label}<input className={control} type="date" required value={draft[key]} onChange={(event) => change(key, event.target.value)} /></label>)}</>}
      <div className="ml-auto flex items-center justify-end gap-2 self-end max-[600px]:ml-0"><button type="button" className="report-button" onClick={() => { const empty = defaultReportFilters(); setDraft(empty); setValidation(''); onApply(empty) }}>Xóa lọc</button><button type="submit" className="report-button report-button-primary">Áp dụng</button></div>
    </div>
    <div className="mt-4 grid grid-cols-3 gap-3 max-[600px]:grid-cols-1">
      {[['category_id', 'Danh mục', 'Categories'], ['brand_id', 'Thương hiệu', 'Brands'], ['product_id', 'Sản phẩm', 'Products']].map(([key, label, source]) => <label key={key} className={field}>{label}<select className={control} value={draft[key]} disabled={loading || !!error} onChange={(event) => change(key, event.target.value)}><option value="">Tất cả</option>{(options[source] ?? []).filter((item) => source !== 'Products' || ((!draft.category_id || item.CategoryId === draft.category_id) && (!draft.brand_id || item.BrandId === draft.brand_id))).map((item) => <option key={item.Id} value={item.Id}>{item.Name}</option>)}</select></label>)}
    </div>
    {(validation || error) && <p role="alert" className="mt-3 mb-0 text-sm text-admin-red">{validation || 'Không tải được danh sách bộ lọc: ' + error}</p>}
    </div>
  </form>
}
