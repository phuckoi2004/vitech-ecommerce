import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import Field from '../../components/shared/Field.jsx'
import Button from '../../components/shared/Button.jsx'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { PRODUCT_STATUSES } from '../../lib/admin-products.js'
import { updateCatalogProduct, deleteVariant } from '../../services/api/products.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { uploadProductImage } from '../services/product-media.js'
import Modal from './Modal.jsx'
import AdminImagePicker from './AdminImagePicker.jsx'
import { sharedBody, sharedForm } from '../lib/product-form.js'
import { PRODUCT_CONTROL, ProductButton } from './ProductUi.jsx'

// Tiptap stays out of the main bundle: this dialog is reachable from the eagerly loaded products page.
const RichTextEditor = lazy(() => import('./RichTextEditor.jsx'))

function FormError({ message }) {
  return message ? <p role="alert" className="mb-3 rounded-[10px] bg-admin-red/5 p-3 text-xs text-admin-red">{message}</p> : null
}

function ChoiceField({ id, label, value, options, onChange, disabled }) {
  return <Field id={id} label={label} required><select id={id} className={PRODUCT_CONTROL} value={value} onChange={(event) => onChange(event.target.value)} required disabled={disabled}>
    <option value="" disabled hidden />{options.map(([key, name]) => <option key={key} value={key}>{name}</option>)}
  </select></Field>
}

function SharedFields({ form, change, categories, brands, disabled, onUploadImage, onUploadBusy }) {
  const categoryOptions = (Array.isArray(categories.data) ? categories.data : []).map((entry) => [entry.CategoryId, entry.Name + (entry.IsActive ? '' : ' (đã ẩn)')])
  const brandOptions = (Array.isArray(brands.data) ? brands.data : []).map((entry) => [entry.BrandId, entry.Name + (entry.IsActive ? '' : ' (đã ẩn)')])
  return <div className="grid min-w-0 grid-cols-2 gap-4">
    <Field id="product-name" label="Tên sản phẩm" required value={form.Name} maxLength={255} onChange={(event) => change('Name', event.target.value)} className="col-span-full" />
    <ChoiceField id="product-category" label="Danh mục" value={form.CategoryId} options={categoryOptions} onChange={(value) => change('CategoryId', value)} disabled={categories.loading || Boolean(categories.error)} />
    <ChoiceField id="product-brand" label="Thương hiệu" value={form.BrandId} options={brandOptions} onChange={(value) => change('BrandId', value)} disabled={brands.loading || Boolean(brands.error)} />
    <Field id="product-warranty" label="Bảo hành (tháng)" type="number" min={0} step={1} required value={form.WarrantyMonths} onChange={(event) => change('WarrantyMonths', event.target.value)} />
    <ChoiceField id="product-status" label="Trạng thái sản phẩm" value={form.Status} options={PRODUCT_STATUSES} onChange={(value) => change('Status', value)} />
    <div className="col-span-full font-sans"><Suspense fallback={<LoadingState label="Đang tải trình soạn thảo…" className="py-4" />}><RichTextEditor id="product-description" label="Mô tả" labelClassName="text-sm font-semibold text-ink-900" disabled={disabled} value={form.Description} onChange={(value) => change('Description', value)} onUploadImage={onUploadImage} onUploadBusy={onUploadBusy} /></Suspense></div>
    <Field id="product-specifications" label="Thông số kỹ thuật (JSON)" hint={'Ví dụ: {"RAM":"16GB","Màn hình":"6.7 inch"}'} className="col-span-full"><textarea id="product-specifications" className={PRODUCT_CONTROL + ' font-mono'} rows={3} value={form.Specifications} onChange={(event) => change('Specifications', event.target.value)} /></Field>
    <div className="col-span-full"><AdminImagePicker images={form.Images} onChange={(images) => change('Images', images)} onUploadBusy={onUploadBusy} hint="Ảnh nằm trong bộ ảnh của sản phẩm." /></div>
  </div>
}

export function ParentPicker({ value, onChange, selected, lookup }) {
  const [search, setSearch] = useState('')
  return <div className="mb-5 rounded-xl border border-admin-border p-4">
    <div className="mb-3 flex items-end gap-2">
      <Field id="parent-search" label="Tìm sản phẩm đã có" type="search" className="min-w-0 flex-1" value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); lookup.search(search.trim()) } }} />
      <ProductButton secondary onClick={() => lookup.search(search.trim())}>Tìm</ProductButton>
    </div>
    {lookup.error ? <ErrorState message={lookup.error} onRetry={lookup.refresh} /> : <ChoiceField id="parent-product" label="Sản phẩm đã có" value={value} onChange={onChange} disabled={lookup.loading}
      options={[...(selected && !lookup.data?.Items.some((entry) => entry.ProductId === selected.ProductId) ? [[selected.ProductId, selected.Name]] : []),
        ...(lookup.data?.Items ?? []).map((entry) => [entry.ProductId, entry.Name])]} />}
    {!lookup.loading && !lookup.error && lookup.data?.Total === 0 && <p className="mt-2 text-xs text-admin-muted">Chưa tìm thấy sản phẩm. Bạn có thể chọn tạo sản phẩm mới.</p>}
    <div className="mt-3 flex items-center justify-between gap-2" role="navigation" aria-label="Phân trang sản phẩm đã có">
      <ProductButton secondary disabled={lookup.loading || lookup.page <= 1} onClick={() => lookup.setPage(lookup.page - 1)}>Trước</ProductButton>
      <span className="text-xs text-admin-muted">Trang {lookup.page} / {Math.max(1, Math.ceil((lookup.data?.Total ?? 0) / 20))}</span>
      <ProductButton secondary disabled={lookup.loading || lookup.page * 20 >= (lookup.data?.Total ?? 0)} onClick={() => lookup.setPage(lookup.page + 1)}>Sau</ProductButton>
    </div>
  </div>
}

function SharedEditor({ product, categories, brands, onClose, onDone, onBusy }) {
  const auth = useInternalAuth()
  const [form, setForm] = useState(() => sharedForm(product))
  const [busy, setBusy] = useState(false), [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const lookupError = categories.error || brands.error
  const uploadDescriptionImage = async (file) => (await auth.withAccessToken((token) => uploadProductImage(token, file))).ImageUrl
  async function save(event) {
    event.preventDefault()
    if (busy || uploading) return
    let body
    try { body = sharedBody(form) } catch (failure) { setError(failure.message); return }
    setError(''); setBusy(true); onBusy(true)
    try {
      await auth.withAccessToken((token) => updateCatalogProduct(token, product.ProductId, body))
      onDone('Đã cập nhật thông tin chung cho các biến thể của sản phẩm.')
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false); onBusy(false) }
  }
  return <form onSubmit={save}>
    <p className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">Thay đổi tên, danh mục, thương hiệu, mô tả, bảo hành, trạng thái và ảnh tại đây áp dụng cho tất cả biến thể của sản phẩm này.</p>
    <FormError message={error || lookupError} />
    {lookupError && <ProductButton secondary onClick={() => { categories.refresh(); brands.refresh() }}>Thử lại danh mục / thương hiệu</ProductButton>}
    <fieldset disabled={busy} className="min-w-0 border-0 p-0"><SharedFields form={form} change={(key, value) => setForm((previous) => ({ ...previous, [key]: value }))} categories={categories} brands={brands} disabled={busy || uploading} onUploadImage={uploadDescriptionImage} onUploadBusy={setUploading} /></fieldset>
    <div className="mt-5 flex justify-end gap-2"><ProductButton secondary disabled={busy} onClick={onClose}>Hủy</ProductButton><ProductButton type="submit" loading={busy} disabled={uploading || categories.loading || brands.loading || Boolean(lookupError)}>Lưu thông tin chung</ProductButton></div>
  </form>
}

// Compatibility for saved links to the former shared-information dialog.
export function ProductDialog({ productId, categories, brands, onClose, onDone }) {
  const detail = useAdminQuery('/admin/products/' + encodeURIComponent(productId))
  const [busy, setBusy] = useState(false)
  return <Modal variant="tailwind" open wide title="Sửa thông tin chung" busy={busy} onClose={onClose}>
    {detail.loading ? <LoadingState label="Đang tải sản phẩm…" /> : detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} /> : detail.data ? <SharedEditor product={detail.data} categories={categories} brands={brands} onBusy={setBusy} onClose={onClose} onDone={onDone} /> : null}
  </Modal>
}

export function ProductDeleteDialog({ variantId, onClose, onDone }) {
  const auth = useInternalAuth()
  const permitted = auth.permissions.includes('products:view') && auth.permissions.includes('products:delete')
  const detail = useAdminQuery('/admin/catalog-items/' + encodeURIComponent(variantId), {}, permitted)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  async function remove() {
    if (!permitted || writing.current || detail.loading || detail.error || !detail.data || detail.data.IsDeleted) return
    writing.current = true
    setBusy(true); setError('')
    try { await auth.withAccessToken((token) => deleteVariant(token, variantId)); if (mounted.current) onDone('Đã xóa biến thể khỏi danh sách kinh doanh.') }
    catch (failure) { if (mounted.current) setError(failure.message) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  if (!permitted) return null
  return <Modal variant="product-delete" open className="w-[366px] min-h-[165px]" title="Xác nhận xóa sản phẩm?" busy={busy} onClose={onClose}>
    <FormError message={error} />{detail.loading ? <LoadingState label="Đang tải sản phẩm…" className="py-2" /> : detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} className="py-2" /> : detail.data?.IsDeleted ? <p role="status" className="mb-3 text-center text-xs text-admin-muted">Biến thể này đã được xóa.</p> : detail.data && <p className="sr-only">Biến thể được chọn: {detail.data.Name}, {detail.data.Color}, SKU {detail.data.Sku}. Chỉ xóa biến thể này; các biến thể khác và lịch sử giao dịch được giữ lại.</p>}
    <div className="flex justify-center gap-[43px]"><Button variant="secondary" className="h-[42px]! w-[100px] cursor-pointer rounded-[9px]! border-[#dbe3ed]! bg-white! px-0! font-admin! text-sm text-admin-red! enabled:hover:bg-red-50!" disabled={busy} onClick={onClose}>Hủy</Button><Button className="h-[42px]! w-[100px] cursor-pointer rounded-[9px]! border-0 bg-admin-red! px-0! font-admin! text-sm text-white enabled:hover:bg-admin-red/90!" loading={busy} disabled={detail.loading || Boolean(detail.error) || !detail.data || detail.data.IsDeleted} onClick={remove}>Xác nhận</Button></div>
  </Modal>
}
