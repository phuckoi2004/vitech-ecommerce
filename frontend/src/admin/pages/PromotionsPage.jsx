import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { Pagination } from '../../components/shared/index.js'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { getPromotionDirectory } from '../services/promotions.js'
import { filterPromotions, promotionFilters, promotionMoney, promotionPeriod, promotionValue, PROMOTION_PAGE_SIZE, PROMOTION_STATUSES, PROMOTION_TYPES } from '../lib/promotions.js'
import AdminTable from '../components/AdminTable.jsx'
import PromotionDialog from '../components/PromotionDialog.jsx'
import { PromotionAction, PromotionButton, PromotionStatus } from '../components/PromotionUi.jsx'
import useCouponRefresh from '../hooks/useCouponRefresh.js'

const CONTROL = 'h-[42px] shrink-0 rounded-[10px] border border-admin-border bg-white px-[13px] text-xs text-admin-text placeholder:text-admin-muted'
function FilterSelect({ label, className, children, ...props }) {
  return <span className={'relative shrink-0 ' + className}><select aria-label={label} title={label} className={CONTROL + ' w-full appearance-none pr-8!'} {...props}>{children}</select><span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[11px] text-admin-muted">▼</span></span>
}

export default function PromotionsPage() {
  const auth = useInternalAuth(), [params, setParams] = useSearchParams(), [notice, setNotice] = useState('')
  const can = (action) => auth.user.Role === 'Admin' && auth.permissions.includes('promotions:' + action)
  const list = useAdminLoad(getPromotionDirectory), filter = promotionFilters(params)
  const rows = filterPromotions(list.data ?? [], filter), page = Math.min(filter.page, Math.max(1, Math.ceil(rows.length / PROMOTION_PAGE_SIZE)))
  function change(key, value) { setParams((previous) => { const next = new URLSearchParams(previous); if (value) next.set(key, value); else next.delete(key); next.delete('page'); return next }, { replace: true }) }
  function open(mode, id) { setParams((previous) => { const next = new URLSearchParams(previous); next.delete('dialog'); next.delete('promotion'); if (mode) { next.set('dialog', mode); if (id) next.set('promotion', id) } return next }) }
  const columns = [
    { key: 'Name', label: 'Tên chương trình', className: 'w-[25%]', render: (value) => <span className="break-words">{value}</span> },
    { key: 'DiscountType', label: 'Loại giảm', className: 'w-[10%]', render: (value) => PROMOTION_TYPES[value] ?? value },
    { key: 'DiscountValue', label: 'Giá trị', className: 'w-[9%]', render: (_, row) => promotionValue(row) },
    { key: 'MinOrderValue', label: 'Đơn tối thiểu', className: 'w-[11.5%]', render: promotionMoney },
    { key: 'period', label: 'Thời gian', className: 'w-[19.5%]', render: (_, row) => <span className="whitespace-nowrap">{promotionPeriod(row)}</span> },
    { key: 'Status', label: 'Trạng thái', className: 'w-[12.5%]', render: (value) => <PromotionStatus value={value} /> },
    { key: 'actions', label: 'Thao tác', className: 'w-[12.5%] text-center', render: (_, row) => <div className="flex items-center justify-center gap-[3px]"><PromotionAction kind="view" name={row.Name} onClick={() => open('view', row.PromotionId)} />{can('update') && <PromotionAction kind="edit" name={row.Name} onClick={() => open('edit', row.PromotionId)} />}{can('delete') && <PromotionAction kind="delete" name={row.Name} onClick={() => open('delete', row.PromotionId)} />}</div> },
  ]
  const mode = params.get('dialog'), id = params.get('promotion')
  const allowed = ['view', 'new', 'edit', 'delete'].includes(mode) && (mode === 'view' || can(({ new: 'create', edit: 'update', delete: 'delete' })[mode]))
  useCouponRefresh(list.refresh, !allowed)
  return <section aria-label="Quản lý khuyến mãi" className="-mt-0.5 flex min-w-0 flex-col gap-[18px] font-admin text-admin-text">
    <header className="flex min-h-[35px] items-center justify-between gap-3"><h2 className="m-0 text-xl leading-[normal] font-bold">Danh sách chương trình khuyến mãi</h2>{can('create') && <PromotionButton className="h-[35px]! px-[15px]!" onClick={() => open('new')}>+ Thêm khuyến mãi</PromotionButton>}</header>
    <form role="search" aria-label="Lọc khuyến mãi" onSubmit={(event) => event.preventDefault()} className="flex min-h-[66px] items-center gap-2.5 rounded-[14px] border border-admin-border bg-white p-3">
      <input type="search" aria-label="Tìm kiếm khuyến mãi" placeholder="Tìm kiếm khuyến mãi..." maxLength={255} className={CONTROL + ' w-[300px]'} value={filter.keyword} onChange={(event) => change('keyword', event.target.value)} />
      <FilterSelect label="Loại giảm" className="w-[160px]" value={filter.type} onChange={(event) => change('type', event.target.value)}><option value="">Tất cả loại giảm</option>{Object.entries(PROMOTION_TYPES).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</FilterSelect>
      <FilterSelect label="Trạng thái khuyến mãi" className="w-[170px]" value={filter.status} onChange={(event) => change('status', event.target.value)}><option value="">Tất cả trạng thái</option>{Object.entries(PROMOTION_STATUSES).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</FilterSelect>
      <p className="m-0 ml-auto text-[11px] font-medium whitespace-nowrap text-admin-muted">Hiển thị {list.loading || list.error ? '—' : rows.length} khuyến mãi</p>
    </form>
    {notice && <p role="status" className="m-0 rounded-lg bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    <div className="overflow-hidden rounded-[14px] border border-admin-border bg-white"><AdminTable columns={columns} rows={rows.slice((page - 1) * PROMOTION_PAGE_SIZE, page * PROMOTION_PAGE_SIZE)} rowKey="PromotionId" label="Danh sách khuyến mãi" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText={filter.keyword || filter.type || filter.status ? 'Không có khuyến mãi phù hợp.' : 'Chưa có chương trình khuyến mãi.'} className="min-w-[920px]! table-fixed [&_th]:h-16! [&_th]:border-b-0! [&_th]:px-3! [&_th]:text-[11px]! [&_td]:h-16! [&_td]:px-3! [&_td]:py-0! [&_td]:text-[11px]! [&_tr:last-child_td]:border-b-0! [&_td:last-child]:px-1!" /></div>
    {!list.loading && !list.error && <div className="[&_button]:h-[38px] [&_button]:rounded-[10px]"><Pagination variant="admin" itemLabel="khuyến mãi" label="Phân trang khuyến mãi" page={page} pageSize={PROMOTION_PAGE_SIZE} total={rows.length} onPageChange={(value) => setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(value)); return next })} /></div>}
    {allowed && (mode === 'new' || id) && <PromotionDialog key={mode + '-' + id} mode={mode} promotionId={id} onClose={() => open(null)} onDone={(message) => { open(null); setNotice(message); list.refresh() }} onEdit={() => open('edit', id)} onDelete={() => open('delete', id)} />}
  </section>
}
