import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Pagination } from '../../components/shared/index.js'
import { formatDate } from '../../lib/format.js'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { getReturnDirectory } from '../services/returns.js'
import { filterReturns, RETURN_PAGE_SIZE, RETURN_STATUSES, returnFilters, returnListSearch, returnTypeLabel } from '../lib/returns.js'
import AdminTable from '../components/AdminTable.jsx'
import { ReturnButton, ReturnStatus } from '../components/ReturnUi.jsx'
import useAutoFilters from '../hooks/useAutoFilters.js'

function ReturnFilters({ filter, onApply }) {
  const { draft, setDraft, formProps } = useAutoFilters({ keyword: filter.keyword, status: filter.status, from: filter.from, to: filter.to }, onApply, {
    validate: (values) => !(values.from && values.to && values.from > values.to),
  })
  const change = (key, value) => setDraft((previous) => ({ ...previous, [key]: value }))
  const control = 'h-10 w-full rounded-lg border border-admin-border bg-white px-3 text-[10px] leading-[normal] font-normal text-admin-text placeholder:text-admin-muted'
  const field = 'flex shrink-0 flex-col gap-1.5 text-[10px] leading-[normal] font-medium'
  const rangeError = draft.from && draft.to && draft.from > draft.to
  return <form role="search" {...formProps}>
    <div className="admin-filterbar flex items-end gap-2.5">
      <label className={field + ' w-[330px]'}>Tìm kiếm<input type="search" aria-label="Tìm mã yêu cầu, khách hàng hoặc sản phẩm" className={control} maxLength={255} placeholder="Mã yêu cầu / khách hàng / sản phẩm" value={draft.keyword} onChange={(event) => change('keyword', event.target.value)} /></label>
      <label className={field + ' w-[180px]'}>Trạng thái<select aria-label="Trạng thái" className={control} value={draft.status} onChange={(event) => change('status', event.target.value)}><option value="">Tất cả trạng thái</option>{RETURN_STATUSES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className={field + ' w-[150px]'}>Từ ngày<input type="date" aria-label="Từ ngày" className={control} value={draft.from} onChange={(event) => change('from', event.target.value)} /></label>
      <label className={field + ' w-[150px]'}>Đến ngày<input type="date" aria-label="Đến ngày" className={control} value={draft.to} onChange={(event) => change('to', event.target.value)} /></label>
      <div className="ml-auto flex shrink-0 items-center gap-2.5 pb-1"><ReturnButton secondary className="text-admin-text!" onClick={() => { const empty = { keyword: '', status: '', from: '', to: '' }; setDraft(empty); onApply(empty) }}>Xóa lọc</ReturnButton></div>
    </div>
    {rangeError && <p role="alert" className="mt-2 mb-0 text-[11px] text-admin-red">Từ ngày không được sau Đến ngày.</p>}
  </form>
}

export default function ReturnsPage() {
  const [params, setParams] = useSearchParams(), navigate = useNavigate()
  const list = useAdminLoad(getReturnDirectory), filter = returnFilters(params)
  const rows = filterReturns(list.data ?? [], filter)
  const lastPage = Math.max(1, Math.ceil(rows.length / RETURN_PAGE_SIZE)), page = Math.min(filter.page, lastPage)
  useEffect(() => {
    if (list.data && !list.loading && !list.error && filter.page > lastPage) setParams((previous) => {
      const next = new URLSearchParams(previous); next.set('page', String(lastPage)); return next
    }, { replace: true })
  }, [list.data, list.loading, list.error, filter.page, lastPage, setParams])
  function apply(values) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      for (const key of ['keyword', 'status', 'from', 'to']) {
        const value = String(values[key] ?? '').trim()
        if (value) next.set(key, value)
        else next.delete(key)
      }
      next.delete('page'); return next
    })
  }
  const columns = [
    { key: 'RequestCode', label: 'Mã yêu cầu', className: 'w-[11.08%]' },
    { key: 'CustomerName', label: 'Khách hàng', className: 'w-[14.18%]' },
    { key: 'ProductName', label: 'Sản phẩm', className: 'w-[20.39%]', render: (name, row) => <span title={[row.Sku, row.VariantInfo].filter(Boolean).join(' • ')}>{name || '—'}</span> },
    { key: 'RequestType', label: 'Loại yêu cầu', className: 'w-[12.41%]', render: returnTypeLabel },
    { key: 'RequestedAt', label: 'Ngày gửi', className: 'w-[9.31%]', render: formatDate },
    { key: 'Status', label: 'Trạng thái', className: 'w-[11.52%]', render: (status) => <ReturnStatus status={status} /> },
    { key: 'actions', label: 'Thao tác', className: 'w-[21.11%]', render: (_, row) => <ReturnButton secondary className="text-admin-text!" aria-label={'Xem chi tiết ' + row.RequestCode} onClick={() => navigate('/admin/returns/' + encodeURIComponent(row.ReturnRequestId) + returnListSearch(params))}>Xem chi tiết</ReturnButton> },
  ]
  return <section aria-label="Quản lý đổi trả" className="-my-1 flex min-w-0 flex-col gap-4 font-admin text-admin-text">
    <header className="flex min-h-[33px] items-center justify-between"><h2 className="m-0 text-xl leading-[normal] font-bold">Danh sách yêu cầu đổi trả</h2><ReturnButton secondary className="text-admin-text!" disabled={list.loading} onClick={list.refresh}>Làm mới</ReturnButton></header>
    <div aria-label="Lọc nhanh trạng thái" className="flex gap-2">{[['', 'Tất cả'], ...RETURN_STATUSES].map(([key, label]) => <button type="button" key={key} aria-pressed={filter.status === key} onClick={() => apply({ ...filter, status: key })} className={'shrink-0 cursor-pointer rounded-[9px] border px-3 py-2 text-[10px] leading-[normal] ' + (filter.status === key ? 'border-admin-blue bg-admin-blue font-semibold text-white' : 'border-admin-border bg-white font-medium text-admin-muted hover:bg-admin-page')}>{label}</button>)}</div>
    <ReturnFilters filter={filter} onApply={apply} />
    <section aria-label="Yêu cầu đổi trả" className="overflow-hidden rounded-xl border border-admin-border bg-white">
      <header className="flex h-11 items-center justify-between px-4"><h3 className="m-0 text-[13px] leading-[normal] font-semibold">Yêu cầu đổi trả</h3><span className="text-[10px] text-admin-muted">{list.loading || list.error ? '—' : rows.length} yêu cầu</span></header>
      <AdminTable columns={columns} rows={rows.slice((page - 1) * RETURN_PAGE_SIZE, page * RETURN_PAGE_SIZE)} rowKey="ReturnRequestId" label="Danh sách yêu cầu đổi trả" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText={filter.keyword || filter.status || filter.from || filter.to ? 'Không có yêu cầu đổi trả phù hợp.' : 'Chưa có yêu cầu đổi trả.'} className="min-w-[1050px] table-fixed [&_th]:h-[62px]! [&_th]:border-b-0! [&_th]:px-2.5! [&_th]:text-[10px]! [&_th]:font-medium! [&_td]:h-[62px]! [&_td]:px-2.5! [&_td]:text-[10px]! [&_td]:leading-[normal] [&_td]:break-words" />
      {!list.loading && !list.error && <div className="px-4 py-[13px] [&_span]:text-[10px]"><Pagination variant="admin" label="Phân trang yêu cầu đổi trả" itemLabel="yêu cầu" page={page} pageSize={RETURN_PAGE_SIZE} total={rows.length} onPageChange={(value) => setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(value)); return next })} /></div>}
    </section>
  </section>
}
