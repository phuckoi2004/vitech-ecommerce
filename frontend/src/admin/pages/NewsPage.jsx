import { useCallback, useEffect, useState } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { Pagination } from '../../components/shared/index.js'
import { getAdminData } from '../../services/api/admin.js'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { getNewsDirectory } from '../services/news.js'
import { purchaseReadBatch } from '../services/purchases.js'
import { NEWS_PAGE_SIZE, NEWS_STATUSES, newsFilter, newsPagePath, newsPublishedTime } from '../lib/news.js'
import AdminTable from '../components/AdminTable.jsx'
import NewsDialog from '../components/NewsDialog.jsx'
import { NewsAction, NewsButton, NewsStatus } from '../components/NewsUi.jsx'
import useAutoFilters from '../hooks/useAutoFilters.js'

const CONTROL = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] text-admin-text placeholder:text-admin-text'
function NewsFilters({ keyword, status, onSearch, onReset }) {
  const { draft, setDraft, formProps } = useAutoFilters({ keyword, status }, (values) => onSearch(values.keyword, values.status))
  return <form role="search" className="admin-filterbar flex items-end gap-2.5 leading-[11px]" {...formProps}>
    <label className="flex w-[360px] flex-col gap-[5px] text-[9px] font-medium text-admin-muted">Tìm kiếm<input type="search" aria-label="Tìm tin tức theo tiêu đề hoặc slug" className={CONTROL} placeholder="Tiêu đề / slug" maxLength={300} value={draft.keyword} onChange={(event) => setDraft({ ...draft, keyword: event.target.value })} /></label>
    <label className="flex w-[190px] flex-col gap-[5px] text-[9px] font-medium text-admin-muted">Trạng thái<select aria-label="Trạng thái tin tức" className={CONTROL} value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="">Tất cả</option>{Object.entries(NEWS_STATUSES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <div className="flex-1" /><NewsButton secondary className="text-admin-text!" onClick={() => { setDraft({ keyword: '', status: '' }); onReset() }}>Xóa lọc</NewsButton>
  </form>
}

export default function NewsPage() {
  const auth = useInternalAuth(), [params, setParams] = useSearchParams(), navigate = useNavigate(), location = useLocation()
  const can = (action) => auth.permissions.includes('news:' + action)
  const list = useAdminLoad(getNewsDirectory, can('view'))
  const filter = newsFilter(params)
  const [notice, setNotice] = useState(location.state?.newsNotice ?? '')
  const filtered = (list.data ?? []).filter((article) => (!filter.status || article.Status === filter.status) && [article.Title, article.Slug].some((text) => text.toLocaleLowerCase('vi').includes(filter.keyword.toLocaleLowerCase('vi'))))
  const pages = Math.max(1, Math.ceil(filtered.length / NEWS_PAGE_SIZE)), page = Math.min(filter.page, pages)
  const rows = filtered.slice((page - 1) * NEWS_PAGE_SIZE, page * NEWS_PAGE_SIZE)
  const creatorIds = JSON.stringify([...new Set(rows.map((row) => row.CreatedByUserId).filter((id) => id && id !== auth.user.UserId))].sort())
  const loadCreators = useCallback(async (token, signal) => {
    const ids = JSON.parse(creatorIds)
    const accounts = await purchaseReadBatch(ids, (id) => getAdminData(token, '/admin/users/' + encodeURIComponent(id), {}, signal), signal)
    return Object.fromEntries(accounts.map((account) => [account.UserId, account.FullName]))
  }, [creatorIds])
  const creators = useAdminLoad(loadCreators, auth.permissions.includes('users:read') && creatorIds !== '[]')
  useEffect(() => {
    if (list.data && !list.error && filter.page > pages) setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(pages)); return next }, { replace: true })
  }, [list.data, list.error, filter.page, pages, setParams])
  function search(keyword, status) {
    setParams((previous) => { const next = new URLSearchParams(previous); next.delete('page'); for (const [key, value] of [['keyword', keyword], ['status', status]]) { if (value) next.set(key, value); else next.delete(key) } return next })
  }
  function open(dialog, id) {
    if (['view', 'new', 'edit'].includes(dialog)) { navigate(newsPagePath(dialog, id, params)); return }
    setParams((previous) => { const next = new URLSearchParams(previous); if (dialog) next.set('dialog', dialog); else next.delete('dialog'); if (id) next.set('article', id); else next.delete('article'); return next })
  }
  function done(message) { setNotice(message); list.refresh(); open(null) }
  const mode = params.get('dialog'), id = params.get('article')
  const allowed = mode === 'view' ? can('view') : mode === 'new' ? can('create') : mode === 'edit' ? can('update') : mode === 'delete' && can('delete')
  if (allowed && ['view', 'new', 'edit'].includes(mode) && (mode === 'new' || id)) return <Navigate to={newsPagePath(mode, id, params)} replace />
  const columns = [
    { key: 'Title', label: 'Tiêu đề', className: 'w-[23.94%]', render: (title) => <span className="break-words">{title}</span> },
    { key: 'Summary', label: 'Tóm tắt', className: 'w-[22.16%]', render: (value) => <span className="break-words whitespace-pre-wrap">{value || '—'}</span> },
    { key: 'CreatedByUserId', label: 'Người tạo', className: 'w-[11.97%]', render: (id, row) => <span className="break-words" title={id}>{row.CreatedByName || (id === auth.user.UserId ? auth.user.FullName : creators.data?.[id]) || (creators.loading ? 'Đang tải…' : '—')}</span> },
    { key: 'Status', label: 'Trạng thái', className: 'w-[10.64%]', render: (value) => <NewsStatus status={value} /> },
    { key: 'PublishedAt', label: 'Thời điểm đăng', className: 'w-[15.51%]', render: newsPublishedTime },
    { key: 'actions', label: 'Thao tác', className: 'w-[15.78%]', render: (_, row) => <div className="flex items-center gap-[3px]"><NewsAction action="view" title={row.Title} onClick={() => open('view', row.NewsArticleId)} />{can('update') && <NewsAction action="edit" title={row.Title} onClick={() => open('edit', row.NewsArticleId)} />}{can('delete') && <NewsAction action="delete" title={row.Title} onClick={() => open('delete', row.NewsArticleId)} />}</div> },
  ]
  return <section aria-label="Quản lý tin tức" className="-mt-1 flex min-w-0 flex-col gap-3.5">
    <header className="flex min-h-[38px] items-center justify-between"><div><h2 className="m-0 text-xl leading-6 font-bold">Danh sách tin tức</h2><p className="mt-0.5 mb-0 text-[10px] leading-[12px] text-admin-muted">Xem, thêm, sửa và xóa tin tức hiển thị cho khách hàng</p></div>{can('create') && <NewsButton onClick={() => open('new')}>+ Thêm tin tức</NewsButton>}</header>
    {notice && <p role="status" className="m-0 rounded-lg bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    <NewsFilters keyword={filter.keyword} status={filter.status} onSearch={search} onReset={() => search('', '')} />
    {creators.error && <p role="alert" className="m-0 text-xs text-admin-red">Chưa tải được tên người tạo. <button type="button" className="cursor-pointer text-admin-blue underline" onClick={creators.refresh}>Thử lại tên người tạo</button></p>}
    <section aria-label="Danh sách tin tức" className="overflow-hidden rounded-xl border border-admin-border bg-white">
      <header className="flex items-center justify-between px-3.5 py-[13px]"><h3 className="m-0 text-[13px] leading-4 font-semibold">Tin tức</h3><span className="text-[9px] text-admin-muted">{list.loading || list.error ? '—' : filtered.length} bài viết</span></header>
      <AdminTable columns={columns} rows={rows} rowKey="NewsArticleId" label="Bảng tin tức" loading={list.loading} error={list.error} onRetry={list.refresh} emptyContent={<div className="flex min-h-[210px] w-full flex-col items-center justify-center gap-2.5 p-[30px]"><h4 className="m-0 text-[15px] leading-[18px] font-semibold">{filter.keyword || filter.status ? 'Không có tin tức phù hợp.' : 'Chưa có tin tức nào'}</h4><p className="m-0 max-w-[410px] text-center text-[10px] leading-3 text-admin-muted">{filter.keyword || filter.status ? 'Không tìm thấy bài viết theo điều kiện đã chọn.' : 'Hệ thống hiện chưa có tin tức trong cơ sở dữ liệu.'}</p></div>} className="min-w-[1000px] table-fixed [&_th]:h-[46px]! [&_th]:border-b-0! [&_th]:px-2! [&_th]:text-[8px]! [&_th]:font-semibold! [&_td]:h-[68px]! [&_td]:px-2! [&_td]:py-0! [&_td]:text-[9px]! [&_tr:last-child_td]:border-b-0!" />
      {!list.loading && !list.error && <div className="border-t border-admin-border px-3.5 py-3 [&_span]:text-[9px] [&_button]:h-[30px] [&_button]:min-w-[30px] [&_button]:rounded-[9px] [&_button]:text-[10px] [&_nav]:gap-[3px] [&_nav_span]:gap-[3px]"><Pagination variant="admin" itemLabel="bài viết" label="Phân trang tin tức" page={page} pageSize={NEWS_PAGE_SIZE} total={filtered.length} onPageChange={(value) => setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(value)); return next })} /></div>}
    </section>
    {allowed && mode === 'delete' && id && <NewsDialog key={id} articleId={id} onClose={() => open(null)} onDone={done} />}
  </section>
}
