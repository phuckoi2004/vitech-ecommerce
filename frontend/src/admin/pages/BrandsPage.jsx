import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Pagination } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import AdminTable from '../components/AdminTable.jsx'
import BrandDialog from '../components/BrandDialogs.jsx'
import { PRODUCT_CONTROL, ProductButton } from '../components/ProductUi.jsx'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { BRAND_PAGE_SIZE, brandFilter } from '../lib/brands.js'

function BrandSearch({ keyword, onSearch }) {
  const [value, setValue] = useState(keyword)
  const [source, setSource] = useState(keyword)
  if (source !== keyword) { setSource(keyword); setValue(keyword) }
  useEffect(() => {
    if (value === keyword) return
    const timer = window.setTimeout(() => onSearch(value.trim()), 400)
    return () => window.clearTimeout(timer)
  }, [value, keyword, onSearch])
  return <form role="search" className="w-[360px] shrink-0" onSubmit={(event) => { event.preventDefault(); onSearch(value.trim()) }}>
    <input type="search" aria-label="Tìm kiếm thương hiệu theo tên" placeholder="Tìm kiếm thương hiệu theo tên..." className={PRODUCT_CONTROL + ' h-[42px] px-[13px] text-xs! placeholder:text-admin-muted'} maxLength={255} value={value} onChange={(event) => setValue(event.target.value)} />
  </form>
}

export default function BrandsPage() {
  const auth = useInternalAuth()
  const [params, setParams] = useSearchParams()
  // This existing endpoint returns the full brand array; filtering/pagination stay in the admin UI.
  const list = useAdminQuery('/brands', { active_only: false })
  const filter = brandFilter(params)
  const [notice, setNotice] = useState('')
  const can = (action) => auth.permissions.includes('brands:' + action)
  const brands = Array.isArray(list.data) ? list.data : []
  const filtered = brands.filter((brand) => brand.Name.toLocaleLowerCase('vi').includes(filter.keyword.toLocaleLowerCase('vi'))
    && (!filter.status || brand.IsActive === (filter.status === 'active')))
  const pages = Math.max(1, Math.ceil(filtered.length / BRAND_PAGE_SIZE))
  const page = Math.min(filter.page, pages)
  useEffect(() => {
    if (list.data && !list.error && filter.page > pages) setParams((previous) => {
      const next = new URLSearchParams(previous); next.set('page', String(pages)); return next
    }, { replace: true })
  }, [list.data, list.error, filter.page, pages, setParams])
  function change(key, value) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'page') next.delete('page')
      return next
    })
  }
  function open(dialog, id) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (dialog) next.set('dialog', dialog)
      else next.delete('dialog')
      if (id) next.set('brand', id)
      else next.delete('brand')
      return next
    })
  }
  function done(message) { setNotice(message); list.refresh(); open(null) }
  const dialog = params.get('dialog')
  const brandId = params.get('brand')
  const permitted = dialog === 'new' ? can('create') : dialog === 'edit' ? can('update') : dialog === 'delete' ? can('delete') : dialog === 'view'
  const columns = [
    { key: 'Name', label: 'Tên thương hiệu', className: 'w-[18.6%]', render: (name) => <span className="break-words">{name}</span> },
    { key: 'Description', label: 'Mô tả', className: 'w-[40.3%]', render: (value) => <span className="block break-words">{value || '—'}</span> },
    { key: 'IsActive', label: 'Trạng thái', className: 'w-[13.8%]', render: (value) => <span className={'inline-block rounded-full px-2.5 py-1.5 text-[11px] font-semibold whitespace-nowrap ' + (value ? 'bg-[#16a34a] text-white' : 'bg-admin-soft text-admin-blue')}>{value ? 'Đang hiển thị' : 'Đã ẩn'}</span> },
    { key: 'actions', label: 'Thao tác', className: 'w-[27.3%]', render: (_, row) => <div className="flex items-center gap-2.5 whitespace-nowrap">
      {[['view', 'Chi tiết', true, 'text-admin-blue'], ['edit', 'Sửa', can('update'), 'text-admin-text'], ['delete', 'Xóa', can('delete'), 'text-admin-red']].filter(([, , allowed]) => allowed).map(([action, text, , color]) => <button key={action} type="button" aria-label={text + ' ' + row.Name} className={'cursor-pointer rounded-sm border-0 bg-transparent p-0 text-[11px] font-semibold hover:underline ' + color} onClick={() => open(action, row.BrandId)}>{text}</button>)}
    </div> },
  ]
  return <section className="flex min-w-0 flex-col gap-[18px]" aria-label="Quản lý thương hiệu">
    <div className="flex min-h-[35px] items-center justify-between gap-4"><h2 className="m-0 text-xl font-bold">Danh sách thương hiệu</h2>{can('create') && <ProductButton className="h-[35px]! px-[15px]!" onClick={() => open('new')}>+ Thêm thương hiệu</ProductButton>}</div>
    {notice && <div className="flex items-center justify-between gap-3 rounded-[10px] bg-green-50 p-3 text-xs text-green-700" role="status">{notice}<button type="button" className="cursor-pointer border-0 bg-transparent text-inherit" onClick={() => setNotice('')} aria-label="Đóng thông báo">×</button></div>}
    <div className="flex items-center gap-3">
      <BrandSearch keyword={filter.keyword} onSearch={(value) => change('keyword', value)} />
      <label className="relative w-[190px] shrink-0"><span className="sr-only">Trạng thái</span><select aria-label="Trạng thái" className={PRODUCT_CONTROL + ' h-[42px] cursor-pointer appearance-none pr-8 text-xs! text-admin-muted'} value={filter.status} onChange={(event) => change('status', event.target.value)}>
        <option value="">Trạng thái: Tất cả</option><option value="active">Đang hiển thị</option><option value="hidden">Đã ẩn</option>
      </select><span className="pointer-events-none absolute top-1/2 right-[13px] -translate-y-1/2 text-[11px] text-admin-muted" aria-hidden="true">▼</span></label>
      <span className="ml-auto text-[11px] font-medium whitespace-nowrap text-admin-muted">{list.loading ? 'Đang tải thương hiệu…' : list.error ? 'Chưa tải được thương hiệu' : 'Hiển thị ' + filtered.length + ' thương hiệu'}</span>
    </div>
    <div className="overflow-hidden rounded-[14px] border border-admin-border bg-white">
      <AdminTable columns={columns} rows={filtered.slice((page - 1) * BRAND_PAGE_SIZE, page * BRAND_PAGE_SIZE)} rowKey="BrandId" label="Danh sách thương hiệu" loading={list.loading} error={list.error} onRetry={list.refresh}
        emptyText={filter.keyword || filter.status ? 'Không có thương hiệu phù hợp.' : 'Chưa có thương hiệu.'}
        className="min-w-[900px] table-fixed [&_th]:h-16! [&_th]:bg-white [&_th]:pr-3! [&_th]:pl-4! [&_th]:font-semibold! [&_td]:h-16! [&_td]:pr-3! [&_td]:pl-4! [&_tr:last-child_td]:border-b-0" />
    </div>
    {!list.loading && !list.error && <div className="[&_button]:h-[35px] [&_button]:min-w-9 [&_button]:rounded-[10px]"><Pagination variant="admin" itemLabel="thương hiệu" label="Phân trang thương hiệu" page={page} pageSize={BRAND_PAGE_SIZE} total={filtered.length} onPageChange={(value) => change('page', String(value))} /></div>}
    {permitted && (dialog === 'new' || brandId) && <BrandDialog key={dialog + '-' + brandId} mode={dialog} brandId={brandId} onClose={() => open(null)} onDone={done} onEdit={() => open('edit', brandId)} />}
  </section>
}
