import { lazy, Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Input } from '../../components/shared/Field.jsx'
import { LoadingState, Pagination } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { formatMoney } from '../../lib/format.js'
import { PRICE_RANGES, PRODUCT_STATUSES, STOCK_FILTERS, productQuery, productStatus } from '../../lib/admin-products.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import AdminTable from '../components/AdminTable.jsx'
import { ProductDialog, ProductDeleteDialog } from '../components/ProductDialogs.jsx'
import { ProductButton, ProductThumbnail } from '../components/ProductUi.jsx'
const ProductWorkspace = lazy(() => import('../components/ProductWorkspace.jsx'))

function SearchProducts({ keyword, onSearch }) {
  const [value, setValue] = useState(keyword)
  const [sourceKeyword, setSourceKeyword] = useState(keyword)
  if (sourceKeyword !== keyword) {
    setSourceKeyword(keyword)
    setValue(keyword)
  }
  useEffect(() => {
    if (value === keyword) return
    const timer = window.setTimeout(() => onSearch(value), 400)
    return () => window.clearTimeout(timer)
  }, [value, keyword, onSearch])
  return <form className="min-w-0 flex-[2_1_300px]" role="search" onSubmit={(event) => { event.preventDefault(); onSearch(value) }}>
    <Input aria-label="Tìm sản phẩm, biến thể hoặc SKU" placeholder="Tìm sản phẩm, biến thể hoặc SKU..." type="search" value={value} maxLength={255} onChange={(event) => setValue(event.target.value)}
      className="h-[42px]! rounded-[10px]! border-admin-border! bg-admin-page! px-3.5! font-admin! text-xs! placeholder:text-admin-muted!" />
  </form>
}

function Filter({ label, value, onChange, options, disabled = false, className = '' }) {
  return <label className={`relative min-w-0 flex-[1_1_106px] ${className}`}><span className="sr-only">{label}</span>
    <select className="h-[42px] w-full cursor-pointer appearance-none rounded-[10px] border border-admin-border bg-admin-page pr-7 pl-3.5 text-xs text-admin-muted disabled:cursor-wait disabled:opacity-60" aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled}>
      <option value="">{label}</option>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
    </select><span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[11px] text-admin-muted" aria-hidden="true">▼</span>
  </label>
}

export default function ProductsPage() {
  const auth = useInternalAuth()
  const [params, setParams] = useSearchParams()
  const query = productQuery(params)
  const list = useAdminQuery('/admin/variants', query)
  const categories = useAdminQuery('/categories', { active_only: false })
  const brands = useAdminQuery('/brands', { active_only: false })
  const [notice, setNotice] = useState('')
  const can = (action) => auth.permissions.includes(`products:${action}`)
  const total = list.data?.Total ?? 0
  const pages = Math.max(1, Math.ceil(total / query.page_size))
  useEffect(() => {
    if (list.data && query.page > pages) setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(pages)); return next }, { replace: true })
  }, [list.data, query.page, pages, setParams])

  function change(key, value) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'page') next.delete('page')
      return next
    })
  }
  function open(dialog, variantId, productId, scope) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (scope) next.set('scope', scope)
      else next.delete('scope')
      if (dialog) next.set('dialog', dialog)
      else next.delete('dialog')
      if (productId) next.set('product', productId)
      else next.delete('product')
      if (variantId) next.set('variant', variantId)
      else next.delete('variant')
      return next
    })
  }
  function done(message) {
    setNotice(message)
    list.refresh()
    open(null)
  }
  const dialog = params.get('dialog')
  const variantId = params.get('variant')
  const productId = params.get('product')
  const permittedDialog = dialog === 'new' ? can('create') : ['edit', 'shared'].includes(dialog) ? can('update') : dialog === 'delete' ? can('delete') : dialog === 'view'
  const columns = [
    { key: 'Name', label: 'Sản phẩm', className: 'w-[25.6%]', render: (name, row) => <div className="flex min-w-0 items-center gap-2.5"><ProductThumbnail key={row.ThumbnailUrl} name={name} src={row.ThumbnailUrl} /><button type="button" className="min-w-0 cursor-pointer border-0 bg-transparent p-0 text-left text-xs font-medium text-admin-text hover:text-admin-blue" onClick={() => open('view', row.ProductVariantId)}><span className="block">{name}</span><span className="mt-1 block text-[11px] font-normal text-admin-muted">{[row.Color, row.Storage].filter(Boolean).join(' · ') || row.VariantName}</span></button></div> },
    { key: 'Sku', label: 'Mã SP', className: 'w-[8.2%]', render: (sku) => <span className="break-all">{sku}</span> },
    { key: 'Category', label: 'Danh mục', className: 'w-[11.9%]', render: (value) => value?.Name ?? '—' },
    { key: 'Brand', label: 'Thương hiệu', className: 'w-[11%]', render: (value) => value?.Name ?? '—' },
    { key: 'Price', label: 'Giá bán', className: 'w-[11.9%]', render: formatMoney },
    { key: 'StockQuantity', label: 'Tồn kho', className: 'w-[8.2%]', render: (value, row) => <strong className={value === 0 ? 'text-admin-red' : row.IsLowStock ? 'text-amber-600' : 'font-semibold'}>{value}</strong> },
    { key: 'Status', label: 'Trạng thái', className: 'w-[11%]', render: (_, row) => { const [text, classes] = productStatus(row); return <span className={`inline-block rounded-full px-2.5 py-1.5 text-[11px] font-semibold whitespace-nowrap ${classes}`}>{text}</span> } },
    { key: 'actions', label: 'Thao tác', className: 'w-[12.2%]', render: (_, row) => <div className="flex items-center gap-[7px] whitespace-nowrap">
      {[['view', 'Xem', true], ['edit', 'Sửa', can('update')], ['delete', 'Xóa', can('delete')]].filter(([, , allowed]) => allowed).map(([action, text]) => <button key={action} type="button" className={`cursor-pointer rounded-sm border-0 bg-transparent p-0 text-[11px] font-semibold hover:underline ${action === 'delete' ? 'text-admin-red' : 'text-admin-blue'}`} aria-label={`${text} ${row.Sku}`} onClick={() => open(action, row.ProductVariantId)}>{text}</button>)}
    </div> },
  ]
  const lookupError = categories.error || brands.error
  if (permittedDialog && ['new', 'view', 'edit'].includes(dialog) && (dialog === 'new' || variantId)) return <Suspense fallback={<LoadingState label="Đang tải trang sản phẩm…" />}><ProductWorkspace key={`${dialog}-${variantId}-${productId}-${params.get('scope')}`} mode={dialog} variantId={variantId} productId={productId} editShared={params.get('scope') === 'shared'} categories={categories} brands={brands} onClose={() => open(null)} onDone={done} onEdit={() => open('edit', variantId)} onEditShared={() => open('edit', variantId, null, 'shared')} onAddVariant={(id) => open('new', null, id)} onNew={() => open('new')} /></Suspense>
  return <section className="flex min-w-0 flex-col gap-[18px]" aria-label="Quản lý danh sách sản phẩm">
    <div className="flex min-h-[46px] flex-wrap items-center justify-between gap-3"><div><h2 className="m-0 text-xl font-bold">Danh sách sản phẩm</h2><p className="mt-[3px] text-xs text-admin-muted">Theo dõi, cập nhật và quản lý sản phẩm đang kinh doanh</p></div>
      {can('create') && <ProductButton className="min-w-[148px]" onClick={() => open('new')}>+&nbsp; Thêm sản phẩm</ProductButton>}
    </div>
    {notice && <div className="flex items-center justify-between gap-3 rounded-[10px] bg-green-50 p-3 text-xs text-green-700" role="status">{notice}<button type="button" className="cursor-pointer border-0 bg-transparent text-inherit" onClick={() => setNotice('')} aria-label="Đóng thông báo">×</button></div>}
    <div className="flex min-w-0 flex-wrap items-center gap-2.5 rounded-[14px] border border-admin-border bg-white p-3">
      <SearchProducts keyword={query.keyword ?? ''} onSearch={(value) => change('keyword', value.trim())} />
      <Filter label="Danh mục" value={query.category_id ?? ''} onChange={(value) => change('category_id', value)} options={(Array.isArray(categories.data) ? categories.data : []).map((item) => [item.CategoryId, item.Name])} disabled={categories.loading || Boolean(categories.error)} className="flex-[1_1_145px]!" />
      <Filter label="Thương hiệu" value={query.brand_id ?? ''} onChange={(value) => change('brand_id', value)} options={(Array.isArray(brands.data) ? brands.data : []).map((item) => [item.BrandId, item.Name])} disabled={brands.loading || Boolean(brands.error)} className="flex-[1_1_145px]!" />
      <Filter label="Giá bán" value={PRICE_RANGES.some(([key]) => key === params.get('price')) ? params.get('price') : ''} onChange={(value) => change('price', value)} options={PRICE_RANGES} />
      <Filter label="Tồn kho" value={query.stock ?? ''} onChange={(value) => change('stock', value)} options={STOCK_FILTERS} />
      <Filter label="Trạng thái" value={query.status ?? ''} onChange={(value) => change('status', value)} options={PRODUCT_STATUSES} />
      <ProductButton secondary onClick={() => setParams({})}>Đặt lại</ProductButton>
    </div>
    {lookupError && <p role="alert" className="text-xs text-admin-red">Không tải được bộ lọc: {lookupError} <button type="button" className="cursor-pointer border-0 bg-transparent text-admin-blue underline" onClick={() => { categories.refresh(); brands.refresh() }}>Thử lại bộ lọc</button></p>}
    <section className="flex min-h-[700px] min-w-0 flex-col gap-3 rounded-[14px] border border-admin-border bg-white p-[18px] max-sm:p-3" aria-label="Sản phẩm">
      <header className="flex min-h-9 flex-wrap items-center gap-2.5"><h3 className="m-0 text-[15px] font-semibold">Sản phẩm</h3><span className="rounded-full bg-admin-soft px-[9px] py-[5px] text-[11px] font-semibold text-admin-blue">{list.loading || list.error ? '—' : total} biến thể</span>
        <span className="ml-auto text-[11px] text-admin-muted">{list.loading ? 'Đang cập nhật dữ liệu…' : list.error ? 'Chưa cập nhật được dữ liệu' : list.updatedAt ? `Cập nhật dữ liệu gần nhất: ${list.updatedAt.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}` : ''}</span>
      </header>
      <AdminTable variant="products" columns={columns} rows={list.data?.Items ?? []} rowKey="ProductVariantId" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText="Chưa có biến thể phù hợp." label="Danh sách sản phẩm" className="min-w-[980px] table-fixed" />
      <div className="mt-auto min-h-8 pt-1">{!list.loading && !list.error && <Pagination variant="admin" itemLabel="biến thể" page={query.page} pageSize={query.page_size} total={total} onPageChange={(value) => change('page', String(value))} />}</div>
    </section>
    {permittedDialog && dialog === 'shared' && productId && <ProductDialog key={`shared-${productId}`} mode="shared" productId={productId} categories={categories} brands={brands} onClose={() => open(null)} onDone={done} />}
    {permittedDialog && dialog === 'delete' && variantId && <ProductDeleteDialog key={variantId} variantId={variantId} onClose={() => open(null)} onDone={done} />}
  </section>
}
