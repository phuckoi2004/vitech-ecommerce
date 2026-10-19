import { useEffect, useState } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { Pagination } from '../../components/shared/index.js'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { getBannerDirectory } from '../services/banners.js'
import { BANNER_PAGE_SIZE, BANNER_STATUSES, bannerFilter, bannerPagePath } from '../lib/banners.js'
import AdminTable from '../components/AdminTable.jsx'
import BannerDialog from '../components/BannerDialog.jsx'
import { BannerAction, BannerButton, BannerImage, BannerLink, BannerStatus } from '../components/BannerUi.jsx'
import useAutoFilters from '../hooks/useAutoFilters.js'

const CONTROL = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] text-admin-text placeholder:text-admin-text'
function BannerFilters({ keyword, status, onSearch, onReset }) {
  const { draft, setDraft, formProps } = useAutoFilters({ keyword, status }, (values) => onSearch(values.keyword, values.status))
  return <form role="search" className="admin-filterbar flex items-end gap-2.5 leading-[11px]" {...formProps}>
    <label className="flex w-[360px] flex-col gap-[5px] text-[9px] font-medium text-admin-muted">Tìm kiếm<input type="search" aria-label="Tìm banner theo tiêu đề" className={CONTROL} placeholder="Tiêu đề banner" maxLength={255} value={draft.keyword} onChange={(event) => setDraft({ ...draft, keyword: event.target.value })} /></label>
    <label className="flex w-[190px] flex-col gap-[5px] text-[9px] font-medium text-admin-muted">Trạng thái<select aria-label="Trạng thái banner" className={CONTROL} value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="">Tất cả</option>{Object.entries(BANNER_STATUSES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <div className="flex-1" /><BannerButton secondary className="text-admin-text!" onClick={() => { setDraft({ keyword: '', status: '' }); onReset() }}>Xóa lọc</BannerButton>
  </form>
}

export default function BannersPage() {
  const auth = useInternalAuth(), [params, setParams] = useSearchParams(), navigate = useNavigate(), location = useLocation()
  const can = (action) => auth.permissions.includes('banners:' + action)
  const list = useAdminLoad(getBannerDirectory, can('view')), filter = bannerFilter(params)
  const [notice, setNotice] = useState(location.state?.bannerNotice ?? '')
  const filtered = (list.data ?? []).filter((banner) => (!filter.status || banner.IsActive === (filter.status === 'active')) && banner.Title.toLocaleLowerCase('vi').includes(filter.keyword.toLocaleLowerCase('vi')))
  const pages = Math.max(1, Math.ceil(filtered.length / BANNER_PAGE_SIZE)), page = Math.min(filter.page, pages)
  const rows = filtered.slice((page - 1) * BANNER_PAGE_SIZE, page * BANNER_PAGE_SIZE)
  useEffect(() => {
    if (list.data && !list.error && filter.page > pages) setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(pages)); return next }, { replace: true })
  }, [list.data, list.error, filter.page, pages, setParams])
  function search(keyword, status) {
    setParams((previous) => { const next = new URLSearchParams(previous); next.delete('page'); for (const [key, value] of [['keyword', keyword], ['status', status]]) { if (value) next.set(key, value); else next.delete(key) } return next })
  }
  function open(dialog, id) {
    if (['view', 'new', 'edit'].includes(dialog)) { navigate(bannerPagePath(dialog, id, params)); return }
    setParams((previous) => { const next = new URLSearchParams(previous); if (dialog) next.set('dialog', dialog); else next.delete('dialog'); if (id) next.set('banner', id); else next.delete('banner'); return next })
  }
  function done(message) { setNotice(message); list.refresh(); open(null) }
  const mode = params.get('dialog'), id = params.get('banner')
  const allowed = mode === 'view' ? can('view') : mode === 'new' ? can('create') : mode === 'edit' ? can('update') : mode === 'delete' && can('delete')
  if (allowed && ['view', 'new', 'edit'].includes(mode) && (mode === 'new' || id)) return <Navigate to={bannerPagePath(mode, id, params)} replace />
  const columns = [
    { key: 'Title', label: 'Tiêu đề', className: 'w-[21.72%]', render: (title) => <span className="break-words">{title}</span> },
    { key: 'ImageUrl', label: 'Hình ảnh', className: 'w-[14.18%]', render: (src, row) => <BannerImage src={src} title={row.Title} /> },
    { key: 'LinkUrl', label: 'Link khi bấm', className: 'w-[24.38%]', render: (value) => <BannerLink value={value} /> },
    { key: 'DisplayOrder', label: 'Thứ tự', className: 'w-[7.98%]', render: (value) => <span className="text-admin-muted">{value}</span> },
    { key: 'IsActive', label: 'Trạng thái', className: 'w-[15.51%]', render: (active) => <BannerStatus active={active} /> },
    { key: 'actions', label: 'Thao tác', className: 'w-[16.23%]', render: (_, row) => <div className="flex items-center gap-[3px]"><BannerAction action="view" title={row.Title} onClick={() => open('view', row.BannerId)} />{can('update') && <BannerAction action="edit" title={row.Title} onClick={() => open('edit', row.BannerId)} />}{can('delete') && <BannerAction action="delete" title={row.Title} onClick={() => open('delete', row.BannerId)} />}</div> },
  ]
  return <section aria-label="Quản lý banner quảng cáo" className="-mt-1 flex min-w-0 flex-col gap-3.5">
    <header className="flex min-h-[38px] items-center justify-between"><div><h2 className="m-0 text-xl leading-6 font-bold">Danh sách banner quảng cáo</h2><p className="mt-0.5 mb-0 text-[10px] leading-[12px] text-admin-muted">Xem, thêm, sửa và xóa banner quảng cáo hiển thị cho khách hàng</p></div>{can('create') && <BannerButton onClick={() => open('new')}>+ Thêm banner</BannerButton>}</header>
    {notice && <p role="status" className="m-0 rounded-lg bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    <BannerFilters keyword={filter.keyword} status={filter.status} onSearch={search} onReset={() => search('', '')} />
    <section aria-label="Danh sách banner quảng cáo" className="overflow-hidden rounded-xl border border-admin-border bg-white">
      <header className="flex items-center justify-between px-3.5 py-[13px]"><h3 className="m-0 text-[13px] leading-4 font-semibold">Banner quảng cáo</h3><span className="text-[9px] text-admin-muted">{list.loading || list.error ? '—' : filtered.length} banner</span></header>
      <AdminTable columns={columns} rows={rows} rowKey="BannerId" label="Bảng banner quảng cáo" loading={list.loading} error={list.error} onRetry={list.refresh} emptyContent={<div className="flex min-h-[210px] w-full flex-col items-center justify-center gap-2.5 p-[30px]"><h4 className="m-0 text-[15px] leading-[18px] font-semibold">{filter.keyword || filter.status ? 'Không có banner phù hợp.' : 'Chưa có banner quảng cáo nào'}</h4><p className="m-0 max-w-[410px] text-center text-[10px] leading-3 text-admin-muted">{filter.keyword || filter.status ? 'Không tìm thấy banner theo điều kiện đã chọn.' : 'Hệ thống hiện chưa có banner quảng cáo trong cơ sở dữ liệu.'}</p></div>} className="min-w-[1000px] table-fixed [&_th]:h-[46px]! [&_th]:border-b-0! [&_th]:px-2! [&_th]:text-[8px]! [&_th]:font-semibold! [&_td]:h-[72px]! [&_td]:px-2! [&_td]:py-0! [&_td]:text-[9px]! [&_tr:last-child_td]:border-b-0!" />
      {!list.loading && !list.error && <div className="border-t border-admin-border px-3.5 py-3 [&_span]:text-[9px] [&_button]:h-[30px] [&_button]:min-w-[30px] [&_button]:rounded-[9px] [&_button]:text-[10px] [&_nav]:gap-[3px] [&_nav_span]:gap-[3px]"><Pagination variant="admin" itemLabel="banner" label="Phân trang banner" page={page} pageSize={BANNER_PAGE_SIZE} total={filtered.length} onPageChange={(value) => setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(value)); return next })} /></div>}
    </section>
    {allowed && mode === 'delete' && id && <BannerDialog key={id} bannerId={id} onClose={() => open(null)} onDone={done} />}
  </section>
}
