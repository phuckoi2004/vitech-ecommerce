import { useCallback, useEffect, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { ErrorState, Pagination } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { formatDate, formatMoney } from '../../lib/format.js'
import { getAdminData } from '../../services/api/admin.js'
import AdminTable from '../components/AdminTable.jsx'
import PurchaseDialog from '../components/PurchaseDialogs.jsx'
import { PRODUCT_CONTROL } from '../components/ProductUi.jsx'
import { PurchaseButton, PurchaseStatus } from '../components/PurchaseUi.jsx'
import { SupplierAction } from '../components/SupplierUi.jsx'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { filterPurchases, PURCHASE_PAGE_SIZE, PURCHASE_TABS, purchaseCancellable, purchaseCsv, purchaseEditable, purchaseFilters, purchaseListSearch, purchaseQuantity } from '../lib/purchases.js'
import { getPurchaseDirectory, getPurchaseVariants, purchaseReadBatch } from '../services/purchases.js'
import { getSupplierDirectory } from '../services/suppliers.js'

function PurchaseFilters({ filter, suppliers, variants, supplierDisabled, productDisabled, onApply, onClear }) {
  const initial = { keyword: filter.keyword, supplier: filter.supplier, product: filter.product, from: filter.from, to: filter.to }
  const source = JSON.stringify(initial)
  const [previous, setPrevious] = useState(source)
  const [draft, setDraft] = useState(initial)
  const [error, setError] = useState('')
  if (previous !== source) { setPrevious(source); setDraft(initial); setError('') }
  const control = PRODUCT_CONTROL + ' h-10 rounded-lg! px-[11px] text-[10px]! font-normal text-admin-muted placeholder:text-admin-muted'
  const products = [...new Map(variants.map((variant) => [variant.ProductId, variant.Name])).entries()]
  function change(key, value) { setDraft((valueBefore) => ({ ...valueBefore, [key]: value })); setError('') }
  return <form role="search" className="flex flex-col gap-2" onSubmit={(event) => { event.preventDefault(); if (draft.from && draft.to && draft.from > draft.to) { setError('Từ ngày không được sau Đến ngày.'); return } onApply(draft) }}>
    <div className="flex items-end gap-[9px]">
      <label className="flex w-[210px] shrink-0 flex-col gap-[5px] text-[10px] leading-[normal] font-medium">Tìm kiếm<input type="search" aria-label="Tìm phiếu nhập theo mã hoặc sản phẩm" className={control} placeholder="Mã phiếu / sản phẩm" maxLength={255} value={draft.keyword} onChange={(event) => change('keyword', event.target.value)} /></label>
      <label className="flex w-[170px] shrink-0 flex-col gap-[5px] text-[10px] leading-[normal] font-medium">Nhà cung cấp<select aria-label="Nhà cung cấp" className={control} disabled={supplierDisabled} value={draft.supplier} onChange={(event) => change('supplier', event.target.value)}><option value="">Tất cả NCC</option>{suppliers.map((item) => <option key={item.SupplierId} value={item.SupplierId}>{item.Name}{!item.IsActive ? ' (Ẩn)' : ''}</option>)}</select></label>
      <label className="flex w-[175px] shrink-0 flex-col gap-[5px] text-[10px] leading-[normal] font-medium">Sản phẩm<select aria-label="Sản phẩm" className={control} disabled={productDisabled} value={draft.product} onChange={(event) => change('product', event.target.value)}><option value="">Tất cả sản phẩm</option>{products.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
      <label className="flex w-[130px] shrink-0 flex-col gap-[5px] text-[10px] leading-[normal] font-medium">Từ ngày<input type="date" aria-label="Từ ngày" className={control + ' px-2!'} value={draft.from} max={draft.to || undefined} onChange={(event) => change('from', event.target.value)} /></label>
      <label className="flex w-[130px] shrink-0 flex-col gap-[5px] text-[10px] leading-[normal] font-medium">Đến ngày<input type="date" aria-label="Đến ngày" className={control + ' px-2!'} value={draft.to} min={draft.from || undefined} onChange={(event) => change('to', event.target.value)} /></label>
      <PurchaseButton secondary className="ml-auto mb-1! shrink-0" onClick={() => { setDraft({ keyword: '', supplier: '', product: '', from: '', to: '' }); setError(''); onClear() }}>Xóa lọc</PurchaseButton><PurchaseButton type="submit" className="mb-1! shrink-0">Tìm kiếm</PurchaseButton>
    </div>{error && <p role="alert" className="m-0 text-xs text-admin-red">{error}</p>}
  </form>
}

export default function PurchasesPage() {
  const auth = useInternalAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const filter = purchaseFilters(params)
  const list = useAdminLoad(getPurchaseDirectory)
  const can = (action) => auth.permissions.includes('purchases:' + action)
  const supplierAccess = auth.permissions.includes('suppliers:view')
  const productAccess = auth.permissions.includes('products:view')
  const suppliers = useAdminLoad(getSupplierDirectory, supplierAccess)
  const catalog = useAdminLoad(getPurchaseVariants, productAccess)
  const missingVariantIds = JSON.stringify([...new Set((list.data ?? []).flatMap((po) => po.Items.map((item) => item.ProductVariantId)))].filter((id) => !catalog.data?.some((variant) => variant.ProductVariantId === id)))
  const readHistoricVariants = useCallback(async (token, signal) => {
    const entries = await purchaseReadBatch(JSON.parse(missingVariantIds), (id) => getAdminData(token, '/admin/variants/' + encodeURIComponent(id), {}, signal), signal)
    const productIds = [...new Set(entries.map((entry) => entry.ProductId))]
    const products = await purchaseReadBatch(productIds, (id) => getAdminData(token, '/admin/products/' + encodeURIComponent(id), {}, signal), signal)
    const productNames = new Map(products.map((product) => [product.ProductId, product.Name]))
    return entries.map((entry) => ({ ...entry, Name: productNames.get(entry.ProductId) }))
  }, [missingVariantIds])
  const historicVariants = useAdminLoad(readHistoricVariants, productAccess && Boolean(list.data && catalog.data) && missingVariantIds !== '[]')
  const variants = { data: [...(catalog.data ?? []), ...(historicVariants.data ?? [])], loading: catalog.loading || historicVariants.loading, error: catalog.error || historicVariants.error, refresh: () => { catalog.refresh(); historicVariants.refresh() } }
  const creatorIds = JSON.stringify([...new Set((list.data ?? []).filter((row) => !row.CreatedByName).map((row) => row.CreatedByUserId).filter((id) => id !== auth.user.UserId))])
  const readCreators = useCallback(async (token, signal) => {
    const ids = JSON.parse(creatorIds)
    const users = await purchaseReadBatch(ids, (id) => getAdminData(token, '/admin/users/' + encodeURIComponent(id), { include_deleted: true }, signal), signal, true)
    return Object.fromEntries(ids.map((id, index) => [id, users[index]?.FullName ?? null]))
  }, [creatorIds])
  const creators = useAdminLoad(readCreators, auth.user.Role === 'Admin' && auth.permissions.includes('users:read') && auth.permissions.includes('users:manage') && creatorIds !== '[]')
  const [notice, setNotice] = useState('')
  const supplierRows = suppliers.data ?? []
  const variantRows = variants.data ?? []
  const names = Object.fromEntries(supplierRows.map((row) => [row.SupplierId, row.Name]))
  const creatorNames = { ...creators.data, ...Object.fromEntries((list.data ?? []).filter((row) => row.CreatedByName).map((row) => [row.CreatedByUserId, row.CreatedByName])), [auth.user.UserId]: auth.user.FullName }
  const filtered = filterPurchases(list.data ?? [], filter, variantRows)
  const pages = Math.max(1, Math.ceil(filtered.length / PURCHASE_PAGE_SIZE))
  const page = Math.min(filter.page, pages)
  const rangeError = filter.from && filter.to && filter.from > filter.to ? 'Từ ngày không được sau Đến ngày.' : ''
  const loading = list.loading || suppliers.loading || variants.loading || creators.loading
  useEffect(() => {
    if (list.data && !loading && !list.error && !rangeError && filter.page > pages) setParams((previousParams) => { const next = new URLSearchParams(previousParams); next.set('page', String(pages)); return next }, { replace: true })
  }, [list.data, loading, list.error, rangeError, filter.page, pages, setParams])
  function apply(values) {
    setParams((previousParams) => { const next = new URLSearchParams(previousParams); for (const [key, value] of Object.entries(values)) if (value?.trim()) next.set(key, value.trim()); else next.delete(key); next.delete('page'); return next })
  }
  function open(mode, id) {
    if (mode === 'view' && id) { navigate('/admin/purchases/' + encodeURIComponent(id) + purchaseListSearch(params)); return }
    if (mode === 'new') { navigate('/admin/purchases/new' + purchaseListSearch(params)); return }
    if (mode === 'edit' && id) { navigate('/admin/purchases/' + encodeURIComponent(id) + '/edit' + purchaseListSearch(params)); return }
    setParams((previousParams) => { const next = new URLSearchParams(previousParams); if (mode) next.set('dialog', mode); else next.delete('dialog'); if (id) next.set('purchase', id); else next.delete('purchase'); return next })
  }
  function changed(message) { setNotice(message); list.refresh(); variants.refresh() }
  function done(message) { changed(message); open(null) }
  function exportReport() {
    if (!can('export') || loading || list.error || rangeError || suppliers.error || variants.error) return
    const url = URL.createObjectURL(new Blob([purchaseCsv(filtered, names, creatorNames)], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'phieu-nhap-' + formatDate(new Date()).split('/').reverse().join('') + '.csv'; document.body.append(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const columns = [
    { key: 'PurchaseOrderCode', label: 'Mã phiếu', className: 'w-[9.75%]', render: (value) => <span className="break-words">{value}</span> },
    { key: 'SupplierId', label: 'Nhà cung cấp', className: 'w-[15.07%]', render: (id) => <span className="break-words">{names[id] ?? '—'}</span> },
    { key: 'CreatedByUserId', label: 'Người tạo', className: 'w-[12.85%]', render: (id) => <span className="break-words">{creatorNames[id] ?? '—'}</span> },
    { key: 'CreatedAt', label: 'Ngày lập', className: 'w-[9.75%]', render: formatDate },
    { key: 'quantity', label: 'Tổng SL', className: 'w-[6.21%]', render: (_, row) => purchaseQuantity(row) },
    { key: 'TotalAmount', label: 'Tổng tiền', className: 'w-[11.52%]', render: formatMoney },
    { key: 'Status', label: 'Trạng thái', className: 'w-[10.64%]', render: (value) => <PurchaseStatus status={value} /> },
    { key: 'actions', label: 'Thao tác', className: 'w-[24.21%]', render: (_, row) => <div className="flex items-center gap-[3px]"><SupplierAction kind="view" name={row.PurchaseOrderCode} onClick={() => open('view', row.PurchaseOrderId)} />{can('update') && <SupplierAction kind="edit" name={row.PurchaseOrderCode} disabled={!purchaseEditable(row)} disabledTitle="Chỉ sửa phiếu chờ xác nhận hoặc bị từ chối" onClick={() => open('edit', row.PurchaseOrderId)} />}{can('delete') && <SupplierAction kind="delete" name={row.PurchaseOrderCode} disabled={!purchaseCancellable(row)} disabledTitle="Phiếu đã nhận hàng hoặc đã kết thúc không thể hủy" onClick={() => open('cancel', row.PurchaseOrderId)} />}</div> },
  ]
  const mode = params.get('dialog'), id = params.get('purchase')
  const permitted = mode === 'new' ? can('create') : mode === 'edit' ? can('update') : mode === 'cancel' ? can('delete') : mode === 'view'
  if (permitted && mode === 'new') return <Navigate replace to={'/admin/purchases/new' + purchaseListSearch(params)} />
  if (permitted && mode === 'edit' && id) return <Navigate replace to={'/admin/purchases/' + encodeURIComponent(id) + '/edit' + purchaseListSearch(params)} />
  return <section aria-label="Quản lý nhập hàng" className="-mt-1 flex min-w-0 flex-col gap-3.5">
    <div className="flex items-center gap-2"><div className="mr-auto"><h2 className="m-0 text-xl leading-[normal] font-bold">Danh sách phiếu nhập</h2><p className="mt-[3px] mb-0 text-[11px] leading-[normal] text-admin-muted">Quản lý phiếu nhập, duyệt / từ chối và tra cứu lịch sử nhập hàng</p></div>{can('export') && <PurchaseButton secondary disabled={loading || Boolean(list.error || rangeError || suppliers.error || variants.error)} onClick={exportReport}>Xuất báo cáo</PurchaseButton>}{can('create') && <PurchaseButton onClick={() => open('new')}>+ Tạo phiếu nhập</PurchaseButton>}</div>
    {notice && <p role="status" className="m-0 rounded-[9px] bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    <div role="group" aria-label="Lọc trạng thái phiếu nhập" className="flex gap-2">{PURCHASE_TABS.map(([value, label]) => <button key={value} type="button" aria-pressed={filter.status === value} className="cursor-pointer rounded-[9px] border border-admin-border bg-white px-[11px] py-2 text-[10px] leading-[normal] font-medium text-admin-muted hover:bg-admin-soft aria-pressed:border-admin-blue aria-pressed:bg-admin-blue aria-pressed:font-semibold aria-pressed:text-white" onClick={() => apply({ status: value })}>{label}</button>)}</div>
    <PurchaseFilters filter={filter} suppliers={supplierRows} variants={variantRows} supplierDisabled={!supplierAccess || suppliers.loading || Boolean(suppliers.error)} productDisabled={!productAccess || variants.loading || Boolean(variants.error)} onApply={apply} onClear={() => apply({ keyword: '', supplier: '', product: '', from: '', to: '', status: '' })} />
    {suppliers.error && <ErrorState title="Chưa tải được nhà cung cấp" message={suppliers.error} onRetry={suppliers.refresh} className="py-2" />}{variants.error && <ErrorState title="Chưa tải được sản phẩm" message={variants.error} onRetry={variants.refresh} className="py-2" />}{creators.error && <ErrorState title="Chưa tải được người tạo" message={creators.error} onRetry={creators.refresh} className="py-2" />}
    <div className="overflow-hidden rounded-xl border border-admin-border bg-white"><div className="flex items-center justify-between gap-3 px-3.5 py-[13px]"><h3 className="m-0 text-sm leading-[normal] font-semibold">Phiếu nhập hàng</h3><span className="text-[10px] font-medium text-admin-muted">{loading ? 'Đang tải…' : list.error || rangeError ? 'Chưa tải được' : filtered.length + ' phiếu'}</span></div>
      <AdminTable columns={columns} rows={filtered.slice((page - 1) * PURCHASE_PAGE_SIZE, page * PURCHASE_PAGE_SIZE)} rowKey="PurchaseOrderId" label="Danh sách phiếu nhập" loading={loading} error={list.error || rangeError} onRetry={list.refresh} emptyText={filter.keyword || filter.status || filter.supplier || filter.product || filter.from || filter.to ? 'Không có phiếu nhập phù hợp.' : 'Chưa có phiếu nhập.'} className="min-w-[1060px] table-fixed [&_th]:h-[58px]! [&_th]:border-b-0! [&_th]:pr-1.5! [&_th]:pl-2! [&_th]:text-[9px]! [&_th]:font-semibold! [&_td]:h-[58px]! [&_td]:pr-1.5! [&_td]:pl-2! [&_td]:text-[10px]! [&_td]:leading-[normal]" />
      {!loading && !list.error && !rangeError && <div className="px-3.5 py-3 [&_span]:text-[10px]"><Pagination variant="admin" itemLabel="phiếu" label="Phân trang phiếu nhập" page={page} pageSize={PURCHASE_PAGE_SIZE} total={filtered.length} onPageChange={(value) => setParams((previousParams) => { const next = new URLSearchParams(previousParams); next.set('page', String(value)); return next })} /></div>}
    </div>
    {permitted && (mode === 'new' || id) && <PurchaseDialog key={mode + '-' + id} mode={mode} purchaseId={id} suppliers={suppliers} variants={variants} creatorNames={creatorNames} onClose={() => open(null)} onDone={done} onChanged={changed} />}
  </section>
}
