import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { Pagination } from '../../components/shared/index.js'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import useCouponRefresh, { useCouponClock } from '../hooks/useCouponRefresh.js'
import { getCouponDirectory } from '../services/coupons.js'
import { COUPON_PAGE_SIZE, COUPON_STATUSES, COUPON_VALIDITIES, couponFilters, couponStatus, couponUsage, filterCoupons } from '../lib/coupons.js'
import { PROMOTION_TYPES, promotionDate, promotionMoney, promotionValue } from '../lib/promotions.js'
import { PromotionButton } from '../components/PromotionUi.jsx'
import { CouponAction, CouponStatus } from '../components/CouponUi.jsx'
import CouponDialog from '../components/CouponDialog.jsx'
import AdminTable from '../components/AdminTable.jsx'

const CONTROL = 'h-[42px] min-w-0 shrink-0 rounded-[10px] border border-admin-border bg-white px-3.5 text-xs leading-[normal] text-admin-muted'
function FilterSelect({ label, className, children, ...props }) {
  return <span className={'relative shrink-0 ' + className}><select aria-label={label} title={label} className={CONTROL + ' w-full appearance-none pr-7!'} {...props}>{children}</select><span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[11px] text-admin-muted">▼</span></span>
}

export default function CouponsPage() {
  const auth = useInternalAuth(), [params, setParams] = useSearchParams()
  const admin = auth.user.Role === 'Admin'
  const can = (action) => admin && auth.permissions.includes('promotions:' + action)
  const list = useAdminLoad(getCouponDirectory, admin), filter = couponFilters(params)
  const [notice, setNotice] = useState('')
  const now = useCouponClock()
  useCouponRefresh(list.refresh, admin && !params.get('dialog'))
  const rows = filterCoupons(list.data?.items ?? [], filter, now)
  const page = Math.min(filter.page, Math.max(1, Math.ceil(rows.length / COUPON_PAGE_SIZE)))
  function change(key, value) { setParams((previous) => { const next = new URLSearchParams(previous); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.delete('page'); return next }, { replace: true }) }
  function open(mode, id) { setNotice(''); setParams((previous) => { const next = new URLSearchParams(previous); next.delete('dialog'); next.delete('coupon'); if (mode) { next.set('dialog', mode); if (id) next.set('coupon', id) } return next }) }
  const columns = [
    { key: 'Code', label: 'Mã voucher', className: 'w-[13%]', render: (value) => <span className="inline-block max-w-full rounded-[7px] bg-admin-soft px-1.5 py-1.5 text-[10px] leading-[normal] font-bold break-words text-admin-blue">{value}</span> },
    { key: 'Name', label: 'Tên voucher', className: 'w-[19%]', render: (value) => <span className="text-[11px] font-medium break-words">{value}</span> },
    { key: 'usage', label: 'Lượt sử dụng', className: 'w-[10.5%]', render: (_, row) => <span className="font-semibold whitespace-nowrap" title={row.UsageLimit == null ? row.UsedCount + ' lượt đã dùng / Không giới hạn' : row.UsedCount + ' lượt đã dùng / ' + row.UsageLimit + ' lượt tối đa'}>{couponUsage(row)}</span> },
    { key: 'discount', label: 'Giá trị', className: 'w-[8.5%]', render: (_, row) => <span className="font-semibold whitespace-nowrap">{promotionValue(row.Promotion)}</span> },
    { key: 'minimum', label: 'Đơn tối thiểu', className: 'w-[10.5%]', render: (_, row) => <span className="whitespace-nowrap">{promotionMoney(row.Promotion.MinOrderValue)}</span> },
    { key: 'period', label: 'Thời gian', className: 'w-[10.5%]', render: (_, row) => <span className="flex flex-col whitespace-nowrap"><span>{promotionDate(row.Promotion.StartDate)}</span><span>{' – ' + promotionDate(row.Promotion.EndDate)}</span></span> },
    { key: 'status', label: 'Trạng thái', className: 'w-[14.5%]', render: (_, row) => <CouponStatus value={couponStatus(row, row.Promotion, now)} /> },
    { key: 'actions', label: 'Thao tác', className: 'w-[13.5%] text-center', render: (_, row) => <div className="flex items-center justify-center gap-[3px]"><CouponAction kind="view" row={row} onClick={() => open('view', row.CouponId)} />{can('update') && <CouponAction kind="edit" row={row} onClick={() => open('edit', row.CouponId)} />}{can('delete') && <CouponAction kind="delete" row={row} onClick={() => open('delete', row.CouponId)} />}</div> },
  ]
  if (!admin) return <p role="alert" className="m-0 rounded-lg bg-red-50 p-4 text-sm text-admin-red">Chỉ quản trị viên được quản lý mã giảm giá.</p>
  const mode = params.get('dialog'), id = params.get('coupon')
  const allowed = ['view', 'new', 'edit', 'delete'].includes(mode) && (mode === 'view' || can(({ new: 'create', edit: 'update', delete: 'delete' })[mode]))
  return <section aria-label="Quản lý mã giảm giá" className="-mt-0.5 flex min-w-0 flex-col gap-[18px] font-admin text-admin-text">
    <header className="flex h-10 items-center justify-between gap-3"><h2 className="m-0 text-xl leading-[normal] font-bold">Danh sách mã giảm giá</h2>{can('create') && <PromotionButton className="px-4! whitespace-nowrap" onClick={() => open('new')}>+ Thêm mã giảm giá</PromotionButton>}</header>
    <form role="search" aria-label="Lọc mã giảm giá" onSubmit={(event) => event.preventDefault()} className="flex h-[66px] items-center gap-2.5 rounded-[14px] border border-admin-border bg-white p-3">
      <input type="search" aria-label="Tìm mã giảm giá" placeholder="Tìm mã hoặc tên voucher..." className={CONTROL + ' w-[280px]'} maxLength={255} value={filter.keyword} onChange={(event) => change('keyword', event.target.value)} />
      <FilterSelect label="Loại giảm giá" className="w-[150px]" value={filter.type} onChange={(event) => change('type', event.target.value)}><option value="">Tất cả loại giảm</option>{Object.entries(PROMOTION_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</FilterSelect>
      <FilterSelect label="Lọc trạng thái mã" className="w-[160px]" value={filter.status} onChange={(event) => change('status', event.target.value)}><option value="">Tất cả trạng thái</option>{Object.entries(COUPON_STATUSES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</FilterSelect>
      <FilterSelect label="Hiệu lực chương trình" className="w-[150px]" value={filter.validity} onChange={(event) => change('validity', event.target.value)}><option value="">Tất cả hiệu lực</option>{Object.entries(COUPON_VALIDITIES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</FilterSelect>
      <PromotionButton secondary className="ml-auto w-[84px]" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Đặt lại</PromotionButton>
    </form>
    {notice && <p role="status" className="m-0 rounded-lg bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    <section aria-label="Mã giảm giá" className="admin-table-inset flex min-h-[620px] min-w-0 flex-col gap-3 rounded-[14px] border border-admin-border bg-white p-[18px]">
      <header className="flex h-9 shrink-0 items-center gap-2.5"><h3 className="m-0 text-[15px] leading-[normal] font-semibold">Mã giảm giá</h3><span className="rounded-full bg-admin-soft px-[9px] py-[5px] text-[11px] leading-[normal] font-semibold text-admin-blue">{list.loading || list.error ? '—' : rows.length} voucher</span></header>
      <AdminTable variant="products" label="Danh sách mã giảm giá" columns={columns} rows={rows.slice((page - 1) * COUPON_PAGE_SIZE, page * COUPON_PAGE_SIZE)} rowKey="CouponId" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText={filter.keyword || filter.promotion || filter.type || filter.status || filter.validity ? 'Không có mã giảm giá phù hợp.' : 'Chưa có mã giảm giá.'} className="min-w-[920px]! table-fixed [&_th]:h-12! [&_th]:px-2! [&_th]:text-[10px]! [&_th]:font-semibold! [&_th:first-child]:pl-[18px]! [&_td]:h-[76px]! [&_td]:px-2! [&_td]:py-1.5! [&_td]:text-[10px]! [&_td:first-child]:pl-[18px]! [&_td:last-child]:pr-[18px]!" />
      {!list.loading && !list.error && <div className="mt-auto flex min-h-10 items-center [&>div]:w-full [&_button]:h-[35px] [&_button]:rounded-[9px]"><Pagination variant="admin" itemLabel="mã giảm giá" label="Phân trang mã giảm giá" page={page} pageSize={COUPON_PAGE_SIZE} total={rows.length} onPageChange={(value) => change('page', String(value))} /></div>}
    </section>
    {allowed && (mode === 'new' || id) && <CouponDialog key={mode + '-' + id} mode={mode} couponId={id} promotionId={filter.promotion} can={can} onClose={() => open(null)} onEdit={() => open('edit', id)} onDelete={() => open('delete', id)} onDone={(message) => { open(null); setNotice(message); list.refresh() }} />}
  </section>
}
