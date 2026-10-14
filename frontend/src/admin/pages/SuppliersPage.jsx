import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Pagination } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import AdminTable from '../components/AdminTable.jsx'
import SupplierDialog from '../components/SupplierDialogs.jsx'
import { PRODUCT_CONTROL } from '../components/ProductUi.jsx'
import { SupplierAction, SupplierButton, SupplierStatus } from '../components/SupplierUi.jsx'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { filterSuppliers, SUPPLIER_PAGE_SIZE, supplierFilters } from '../lib/suppliers.js'
import { getSupplierDirectory } from '../services/suppliers.js'

function SupplierFilters({ keyword, status, onApply, onClear }) {
  const [draft, setDraft] = useState({ keyword, status })
  const [source, setSource] = useState({ keyword, status })
  if (source.keyword !== keyword || source.status !== status) { setSource({ keyword, status }); setDraft({ keyword, status }) }
  const control = PRODUCT_CONTROL + ' h-10 rounded-lg! px-[11px] text-[10px]! font-normal placeholder:text-admin-muted'
  return <form role="search" className="flex items-end gap-2.5" onSubmit={(event) => { event.preventDefault(); onApply(draft.keyword.trim(), draft.status) }}>
    <label className="flex w-[360px] shrink-0 flex-col gap-[5px] text-[10px] leading-[normal] font-medium">Tìm kiếm<input type="search" aria-label="Tìm nhà cung cấp theo mã, tên, email hoặc số điện thoại" placeholder="Mã / tên / email / SĐT" maxLength={255} className={control} value={draft.keyword} onChange={(event) => setDraft((previous) => ({ ...previous, keyword: event.target.value }))} /></label>
    <label className="flex w-[190px] shrink-0 flex-col gap-[5px] text-[10px] leading-[normal] font-medium">Trạng thái<span className="relative"><select aria-label="Trạng thái" className={control + ' cursor-pointer appearance-none pr-8 text-admin-muted'} value={draft.status} onChange={(event) => setDraft((previous) => ({ ...previous, status: event.target.value }))}><option value="">Tất cả trạng thái</option><option value="active">Hoạt động</option><option value="hidden">Ẩn</option></select><span aria-hidden="true" className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[10px] text-admin-muted">▼</span></span></label>
    <SupplierButton secondary className="ml-auto mb-1!" onClick={() => { setDraft({ keyword: '', status: '' }); onClear() }}>Xóa lọc</SupplierButton><SupplierButton type="submit" className="mb-1!">Tìm kiếm</SupplierButton>
  </form>
}

export default function SuppliersPage() {
  const auth = useInternalAuth()
  const [params, setParams] = useSearchParams()
  const list = useAdminLoad(getSupplierDirectory)
  const filter = supplierFilters(params)
  const [notice, setNotice] = useState('')
  const can = (action) => auth.permissions.includes('suppliers:' + action)
  const filtered = filterSuppliers(list.data ?? [], filter)
  const pages = Math.max(1, Math.ceil(filtered.length / SUPPLIER_PAGE_SIZE))
  const page = Math.min(filter.page, pages)
  useEffect(() => {
    if (list.data && !list.loading && !list.error && filter.page > pages) setParams((previous) => {
      const next = new URLSearchParams(previous); next.set('page', String(pages)); return next
    }, { replace: true })
  }, [list.data, list.loading, list.error, filter.page, pages, setParams])

  function apply(keyword, status) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      for (const [key, value] of [['keyword', keyword], ['status', status]]) if (value) next.set(key, value); else next.delete(key)
      next.delete('page')
      return next
    })
  }
  function open(mode, id) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (mode) next.set('dialog', mode); else next.delete('dialog')
      if (id) next.set('supplier', id); else next.delete('supplier')
      return next
    })
  }
  function done(message) { setNotice(message); list.refresh(); open(null) }
  const mode = params.get('dialog')
  const supplierId = params.get('supplier')
  const permitted = mode === 'new' ? can('create') : mode === 'edit' ? can('update') : mode === 'delete' ? can('delete') && can('update') : mode === 'view'
  const columns = [
    { key: 'SupplierCode', label: 'Mã NCC', className: 'w-[9.75%]', render: (value) => <span className="break-words">{value}</span> },
    { key: 'Name', label: 'Tên nhà cung cấp', className: 'w-[17.73%]', render: (value) => <span className="break-words">{value}</span> },
    { key: 'contact', label: 'Liên hệ', className: 'w-[21.28%]', render: (_, row) => <div className="break-words"><span className="block">{row.PhoneNumber}</span><span className="block">{row.Email || '—'}</span></div> },
    { key: 'TaxCode', label: 'Mã số thuế', className: 'w-[10.64%]', render: (value) => <span className="break-words">{value || '—'}</span> },
    { key: 'IsActive', label: 'Trạng thái', className: 'w-[9.75%]', render: (value) => <SupplierStatus active={value} /> },
    { key: 'actions', label: 'Thao tác', className: 'w-[30.85%]', render: (_, row) => <div className="flex items-center gap-[3px]"><SupplierAction kind="view" name={row.Name} onClick={() => open('view', row.SupplierId)} />{can('update') && <SupplierAction kind="edit" name={row.Name} onClick={() => open('edit', row.SupplierId)} />}{can('delete') && can('update') && <SupplierAction kind="delete" name={row.Name} disabled={!row.IsActive} onClick={() => open('delete', row.SupplierId)} />}</div> },
  ]
  return <section className="-mt-1 flex min-w-0 flex-col gap-3.5" aria-label="Quản lý nhà cung cấp">
    <div className="flex items-center justify-between gap-4"><div><h2 className="m-0 text-xl leading-[normal] font-bold">Danh sách nhà cung cấp</h2><p className="mt-[3px] mb-0 text-[11px] leading-[normal] text-admin-muted">Xem, thêm, sửa và xóa mềm thông tin nhà cung cấp</p></div>{can('create') && <SupplierButton onClick={() => open('new')}>+ Thêm nhà cung cấp</SupplierButton>}</div>
    {notice && <div role="status" className="flex items-center justify-between gap-3 rounded-[9px] bg-green-50 p-3 text-xs text-green-700">{notice}<button type="button" className="cursor-pointer border-0 bg-transparent text-inherit" aria-label="Đóng thông báo" onClick={() => setNotice('')}>×</button></div>}
    <SupplierFilters keyword={filter.keyword} status={filter.status} onApply={apply} onClear={() => apply('', '')} />
    <div className="overflow-hidden rounded-xl border border-admin-border bg-white">
      <div className="flex items-center justify-between gap-3 px-3.5 py-[13px]"><h3 className="m-0 text-sm leading-[normal] font-semibold">Nhà cung cấp</h3><span className="text-[10px] font-medium text-admin-muted">{list.loading ? 'Đang tải…' : list.error ? 'Chưa tải được' : filtered.length + ' nhà cung cấp'}</span></div>
      <AdminTable columns={columns} rows={filtered.slice((page - 1) * SUPPLIER_PAGE_SIZE, page * SUPPLIER_PAGE_SIZE)} rowKey="SupplierId" label="Danh sách nhà cung cấp" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText={filter.keyword || filter.status ? 'Không có nhà cung cấp phù hợp.' : 'Chưa có nhà cung cấp.'}
        className="min-w-[940px] table-fixed [&_th]:h-[62px]! [&_th]:border-b-0! [&_th]:bg-white [&_th]:pr-1.5! [&_th]:pl-2! [&_th]:text-[9px]! [&_th]:font-semibold! [&_td]:h-[62px]! [&_td]:pr-1.5! [&_td]:pl-2! [&_td]:text-[10px]! [&_td]:leading-[normal]" />
      {!list.loading && !list.error && <div className="px-3.5 py-3 [&_button]:h-[33px] [&_button]:rounded-[9px] [&_button]:text-admin-text [&_button[aria-current=page]]:border-admin-red! [&_button[aria-current=page]]:bg-admin-red! [&_button[aria-current=page]]:text-white! [&_span]:text-[10px]"><Pagination variant="admin" itemLabel="nhà cung cấp" label="Phân trang nhà cung cấp" page={page} pageSize={SUPPLIER_PAGE_SIZE} total={filtered.length} onPageChange={(value) => setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(value)); return next })} /></div>}
    </div>
    {permitted && (mode === 'new' || supplierId) && <SupplierDialog key={mode + '-' + supplierId} mode={mode} supplierId={supplierId} onClose={() => open(null)} onDone={done} onEdit={() => open('edit', supplierId)} />}
  </section>
}
