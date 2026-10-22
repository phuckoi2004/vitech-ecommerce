import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ErrorState, Pagination } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import AdminTable from '../components/AdminTable.jsx'
import ReviewDialog from '../components/ReviewDialog.jsx'
import { ReviewButton, ReviewRating } from '../components/ReviewUi.jsx'
import { SupplierAction } from '../components/SupplierUi.jsx'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { filterReviews, REVIEW_PAGE_SIZE, REVIEW_PERIODS, reviewFilters, reviewTimestamp } from '../lib/reviews.js'
import { getReviewDirectory } from '../services/reviews.js'

function ReviewFilters({ filter, onApply, onClear }) {
  const source = filter.period + '-' + filter.rating
  const [previous, setPrevious] = useState(source)
  const [draft, setDraft] = useState({ period: filter.period, rating: filter.rating })
  if (previous !== source) { setPrevious(source); setDraft({ period: filter.period, rating: filter.rating }) }
  const control = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] font-normal text-admin-text'
  return <form role="search" aria-label="Lọc đánh giá" className="flex items-end gap-2.5" onSubmit={(event) => { event.preventDefault(); onApply(draft) }}>
    <label className="flex w-[220px] shrink-0 flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">Thời gian<select aria-label="Thời gian" className={control} value={draft.period} onChange={(event) => setDraft({ ...draft, period: event.target.value })}>{REVIEW_PERIODS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label className="flex w-[190px] shrink-0 flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">Số sao<select aria-label="Số sao" className={control} value={draft.rating} onChange={(event) => setDraft({ ...draft, rating: event.target.value })}><option value="">Tất cả số sao</option>{[5, 4, 3, 2, 1].map((value) => <option key={value} value={value}>{value} sao</option>)}</select></label>
    <ReviewButton secondary className="ml-auto shrink-0" onClick={() => { setDraft({ period: '', rating: '' }); onClear() }}>Xóa lọc</ReviewButton><ReviewButton type="submit" className="shrink-0">Áp dụng</ReviewButton>
  </form>
}

export default function ReviewsPage() {
  const auth = useInternalAuth()
  const [params, setParams] = useSearchParams()
  const canView = ['Admin', 'Staff'].includes(auth.user.Role) && auth.permissions.includes('reviews:view')
  const productsAllowed = auth.permissions.includes('products:view')
  const list = useAdminLoad(getReviewDirectory, canView && productsAllowed)
  const filter = reviewFilters(params)
  const rows = list.data ?? []
  const filtered = filterReviews(rows, filter)
  const pages = Math.max(1, Math.ceil(filtered.length / REVIEW_PAGE_SIZE))
  const page = Math.min(filter.page, pages)
  const [notice, setNotice] = useState('')
  const canDelete = canView && auth.permissions.includes('reviews:delete')
  useEffect(() => {
    if (list.data && !list.loading && !list.error && filter.page > pages) setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(pages)); return next }, { replace: true })
  }, [list.data, list.loading, list.error, filter.page, pages, setParams])
  function apply(values) { setParams((previous) => { const next = new URLSearchParams(previous); for (const [key, value] of Object.entries(values)) if (value) next.set(key, value); else next.delete(key); next.delete('page'); return next }) }
  function open(mode, id) { setParams((previous) => { const next = new URLSearchParams(previous); if (mode) next.set('dialog', mode); else next.delete('dialog'); if (id) next.set('review', id); else next.delete('review'); return next }) }
  function done(message) { setNotice(message); list.refresh(); open(null) }
  const mode = params.get('dialog'), id = params.get('review')
  const columns = [
    { key: 'User', label: 'Khách hàng', className: 'w-[14.18%]', render: (user) => <span className="break-words">{user?.FullName ?? '—'}</span> },
    { key: 'ProductName', label: 'Sản phẩm', className: 'w-[21.28%]', render: (name) => <span className="break-words">{name ?? '—'}</span> },
    { key: 'Rating', label: 'Số sao', className: 'w-[9.75%]', render: (value) => <ReviewRating value={value} /> },
    { key: 'Content', label: 'Bình luận', className: 'w-[31.92%]', render: (content, row) => <div><span className="line-clamp-2 break-words whitespace-pre-wrap" title={content}>{content || '—'}</span>{row.IsDeleted && <span className="mt-1 inline-block rounded bg-admin-page px-1.5 py-0.5 text-[9px] font-medium text-admin-muted">Đã ẩn</span>}</div> },
    { key: 'CreatedAt', label: 'Thời gian đánh giá', className: 'w-[13.30%]', render: reviewTimestamp },
    { key: 'actions', label: 'Thao tác', className: 'w-[9.57%]', render: (_, row) => <div className="flex items-center gap-[3px]"><SupplierAction kind="view" name={'đánh giá của ' + (row.User?.FullName ?? 'khách hàng')} onClick={() => open('view', row.ReviewId)} />{canDelete && <SupplierAction kind="delete" name={'đánh giá của ' + (row.User?.FullName ?? 'khách hàng')} disabled={row.IsDeleted} disabledTitle="Đánh giá đã được ẩn" onClick={() => open('delete', row.ReviewId)} />}</div> },
  ]
  if (!canView) return <ErrorState title="Không có quyền truy cập" message="Chức năng quản lý đánh giá hiện chỉ dành cho quản trị viên." />
  if (!productsAllowed) return <ErrorState title="Chưa thể tải danh sách đánh giá" message="Bạn cần quyền xem sản phẩm để tải danh sách đánh giá bằng API hiện có." />
  return <section aria-label="Quản lý đánh giá" className="-mt-1 flex min-w-0 flex-col gap-3.5">
    <h2 className="m-0 text-xl leading-6 font-bold">Danh sách đánh giá</h2>
    {notice && <p role="status" className="m-0 rounded-[9px] bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    <ReviewFilters filter={filter} onApply={apply} onClear={() => apply({ period: '', rating: '' })} />
    <div className="overflow-hidden rounded-xl border border-admin-border bg-white"><div className="flex items-center justify-between px-3.5 py-[13px]"><h3 className="m-0 text-[13px] leading-4 font-semibold">Đánh giá &amp; bình luận</h3><span className="text-[9px] leading-[11px] text-admin-muted">{list.loading ? 'Đang tải…' : list.error ? 'Chưa tải được' : filtered.length + ' đánh giá'}</span></div>
      <AdminTable columns={columns} rows={filtered.slice((page - 1) * REVIEW_PAGE_SIZE, page * REVIEW_PAGE_SIZE)} rowKey="ReviewId" label="Danh sách đánh giá" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText={filter.period || filter.rating ? 'Không có đánh giá phù hợp.' : 'Chưa có đánh giá.'} className="min-w-[1000px] table-fixed [&_th]:h-[46px]! [&_th]:border-b-0! [&_th]:px-2! [&_th]:text-xs! [&_th]:font-semibold! [&_td]:h-[72px]! [&_td]:px-2! [&_td]:text-[9px]! [&_td]:leading-[normal]" />
      {!list.loading && !list.error && <div className="px-3.5 py-3 [&_span]:text-[9px]"><Pagination variant="admin" label="Phân trang đánh giá" itemLabel="đánh giá" page={page} pageSize={REVIEW_PAGE_SIZE} total={filtered.length} onPageChange={(value) => setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(value)); return next })} /></div>}
    </div>
    {id && (mode === 'view' || (mode === 'delete' && canDelete)) && <ReviewDialog key={mode + '-' + id} mode={mode} reviewId={id} productName={rows.find((row) => row.ReviewId === id)?.ProductName} onClose={() => open(null)} onDone={done} onRefresh={list.refresh} />}
  </section>
}
