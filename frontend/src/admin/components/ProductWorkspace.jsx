import { useEffect, useRef, useState } from 'react'
import Button from '../../components/shared/Button.jsx'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { PRODUCT_STATUSES, productStatus } from '../../lib/admin-products.js'
import { formatMoney } from '../../lib/format.js'
import { createCatalogItem, updateCatalogItem, updateCatalogProduct } from '../../services/api/products.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { uploadProductImage } from '../services/product-media.js'
import AdminImagePicker from './AdminImagePicker.jsx'
import VariantImageSelection from './VariantImageSelection.jsx'
import Modal from './Modal.jsx'
import { ParentPicker, ProductDeleteDialog } from './ProductDialogs.jsx'
import { sharedBody, sharedForm } from '../lib/product-form.js'
import { ProductButton } from './ProductUi.jsx'
import RichTextContent from '../../components/shared/RichTextContent.jsx'
import RichTextEditor from './RichTextEditor.jsx'

const CARD = 'min-w-0 rounded-[14px] border border-admin-border bg-white p-5'
const CONTROL = 'h-[42px] w-full rounded-[9px] border border-admin-border bg-white px-3 font-admin text-xs text-admin-text placeholder:text-admin-muted disabled:bg-admin-page disabled:text-admin-muted'

function ProductField({ id, label, children, ...props }) {
  return <div className="flex min-w-0 flex-col gap-[7px]"><label htmlFor={id} className="text-xs font-medium">{label}</label>{children ?? <input id={id} className={CONTROL} {...props} />}</div>
}

function ProductSelect({ id, label, options, ...props }) {
  return <ProductField id={id} label={label}><select id={id} className={CONTROL} {...props}><option value="" disabled hidden />{options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></ProductField>
}

function ProductPhoto({ src, name, className = '' }) {
  const [failed, setFailed] = useState(false)
  return src && !failed ? <img src={src} alt={name} onError={() => setFailed(true)} className={'h-full w-full object-contain ' + className} /> : <div className="grid h-full w-full place-items-center rounded-xl bg-admin-page text-xs text-admin-muted">Chưa có ảnh sản phẩm</div>
}

export function ProductGallery({ item }) {
  const images = item.VariantImages ?? (item.Images?.length ? item.Images : item.ThumbnailUrl ? [{ ImageUrl: item.ThumbnailUrl, IsDefault: true }] : [])
  const [selected, setSelected] = useState(() => Math.max(0, images.findIndex((image) => image.IsDefault)))
  const image = images[selected] ?? images[0]
  return <div className={CARD + ' flex h-[467px] flex-col gap-[25px] pt-[37px]'} aria-label="Ảnh sản phẩm">
    <div className="h-[300px] w-full shrink-0"><ProductPhoto key={image?.ImageUrl} src={image?.ImageUrl} name={item.Name} /></div>
    {images.length > 0 && <div className="flex gap-2.5 overflow-x-auto pb-1" aria-label="Chọn ảnh sản phẩm">{images.map((entry, index) => <button key={index} type="button" aria-label={'Xem ảnh ' + (index + 1)} aria-pressed={index === selected} className={`size-[68px] shrink-0 cursor-pointer rounded-[9px] border bg-white p-1 ${index === selected ? 'border-admin-red' : 'border-admin-border'}`} onClick={() => setSelected(index)}><ProductPhoto key={entry.ImageUrl} src={entry.ImageUrl} name={item.Name + ' - ảnh ' + (index + 1)} /></button>)}</div>}
  </div>
}

function ProductDetailsPage({ item, onClose, onDone, onEdit, onEditShared, onAddVariant, onNew }) {
  const auth = useInternalAuth(), [deleting, setDeleting] = useState(false)
  const can = (action) => auth.permissions.includes('products:' + action)
  const [status, statusClasses] = productStatus(item)
  return <section className="-mt-0.5 flex min-w-0 flex-col gap-5" aria-label="Chi tiết sản phẩm">
    <header className="flex h-[41px] items-center justify-between"><h2 className="m-0 text-xl font-bold">Thông tin chi tiết sản phẩm</h2><ProductButton secondary className="text-admin-text!" onClick={onClose}>Quay lại</ProductButton></header>
    <div className="grid grid-cols-[360px_minmax(0,1fr)] items-start gap-5">
      <ProductGallery item={item} />
      <article className={CARD + ' flex flex-col gap-[18px] px-6 py-[22px]'}>
        <div><h3 className="m-0 text-[22px] leading-normal font-bold break-words">{item.Name}</h3><p className="mt-[5px] mb-0 text-xs font-medium text-admin-muted">Mã sản phẩm: {item.Sku}</p>{item.IsDefaultVariant && <p className="mt-2 mb-0 text-xs font-semibold text-admin-blue">Biến thể mặc định</p>}</div>
        <hr className="m-0 w-full border-0 border-t border-admin-border" />
        <dl className="m-0 flex flex-col gap-3 text-xs">{[
          ['Danh mục', item.Category?.Name], ['Thương hiệu', item.Brand?.Name], ['Giá bán', formatMoney(item.Price)], ['Số lượng tồn kho', item.StockQuantity + ' sản phẩm'],
          ['Trạng thái', status === 'Đang bán' ? 'Còn hàng' : status], ['Màu sắc', item.Color], ['Dung lượng', item.Storage],
        ].map(([label, value]) => <div key={label} className="grid grid-cols-[180px_minmax(0,1fr)] gap-2"><dt className="font-medium text-admin-muted">{label}</dt><dd className={'m-0 font-semibold break-words ' + (label === 'Trạng thái' ? statusClasses + ' w-fit rounded-md px-2 py-1' : '')}>{value ?? '—'}</dd></div>)}</dl>
        <div><h4 className="m-0 text-[13px] font-semibold">Mô tả sản phẩm</h4><RichTextContent value={item.Description} className="mt-[7px] max-h-[420px] overflow-y-auto" fallback={<p className="mt-[7px] mb-0 text-xs leading-normal text-admin-muted">Chưa có mô tả sản phẩm.</p>} /></div>
        <details className="text-xs"><summary className="cursor-pointer font-semibold">Thông tin bổ sung</summary><dl className="mt-3 grid grid-cols-[180px_1fr] gap-y-3"><dt>Bảo hành</dt><dd>{item.WarrantyMonths} tháng</dd><dt>Ngưỡng cảnh báo tồn</dt><dd>{item.MinStockLevel}</dd><dt>Quản lý Serial / IMEI</dt><dd>{item.IsSerialTracked ? 'Có' : 'Không'}</dd></dl>{item.Specifications && <pre className="overflow-auto rounded-lg bg-admin-page p-3">{JSON.stringify(item.Specifications, null, 2)}</pre>}</details>
      </article>
    </div>
    <footer className="flex items-center gap-2.5">{can('delete') && <ProductButton secondary className="border-admin-red! text-admin-red!" onClick={() => setDeleting(true)}>Xóa sản phẩm</ProductButton>}<div className="flex-1" />{can('create') && <ProductButton secondary className="text-admin-text!" onClick={onNew}>Thêm sản phẩm mới</ProductButton>}{can('update') && <ProductButton onClick={onEdit}>Sửa chi tiết sản phẩm</ProductButton>}</footer>
    <div className="flex justify-end gap-3">{can('create') && <button type="button" className="cursor-pointer text-xs text-admin-blue hover:underline" onClick={() => onAddVariant(item.ProductId)}>Thêm biến thể cùng sản phẩm</button>}{can('update') && <button type="button" className="cursor-pointer text-xs text-admin-blue hover:underline" onClick={() => onEditShared(item.ProductId)}>Sửa thông tin chung</button>}</div>
    {deleting && <ProductDeleteDialog variantId={item.ProductVariantId} onClose={() => setDeleting(false)} onDone={onDone} />}
  </section>
}

function ProductFormPage({ item, presetProductId, editShared, categories, brands, onClose, onDone }) {
  const auth = useInternalAuth()
  const [target, setTarget] = useState(presetProductId ? 'existing' : 'new'), [parentId, setParentId] = useState(presetProductId ?? '')
  const [keyword, setKeyword] = useState(''), [page, setPage] = useState(1)
  const [editingShared, setEditingShared] = useState(Boolean(editShared))
  const lookup = useAdminQuery('/admin/products', { keyword, page, page_size: 20 }, !item && target === 'existing')
  const parent = useAdminQuery('/admin/products/' + encodeURIComponent(parentId), {}, !item && target === 'existing' && Boolean(parentId))
  const [shared, setShared] = useState(() => sharedForm(item))
  const [galleries, setGalleries] = useState({}), [selections, setSelections] = useState({})
  const [makeDefault, setMakeDefault] = useState(item?.IsDefaultVariant ?? false)
  const [form, setForm] = useState(() => ({ Sku: item?.Sku ?? '', Color: item?.Color ?? '', Storage: item?.Storage ?? '', Price: item?.Price ?? '', MinStockLevel: item?.MinStockLevel ?? 0, IsActive: item?.IsActive ?? true, IsSerialTracked: item?.IsSerialTracked ?? false }))
  const [busy, setBusy] = useState(false), [uploading, setUploading] = useState(false), [error, setError] = useState(''), [pending, setPending] = useState(null)
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const newProduct = !item && target === 'new', commonEditable = newProduct || editingShared
  const common = !item && !newProduct ? sharedForm(parent.data) : shared
  const galleryKey = item ? item.ProductVariantId : newProduct ? 'new' : parentId
  const originalImages = item?.Images ?? parent.data?.Images ?? []
  const gallery = commonEditable ? shared.Images : galleries[galleryKey] ?? originalImages
  const originalSelection = item?.VariantImages ?? (item ? item.Images : []) ?? []
  const choice = selections[galleryKey] ?? { urls: newProduct ? gallery.map((image) => image.ImageUrl) : originalSelection.map((image) => image.ImageUrl), defaultUrl: (originalSelection.find((image) => image.IsDefault) ?? originalSelection[0])?.ImageUrl }
  const selectedUrls = choice.urls.filter((url) => gallery.some((image) => image.ImageUrl === url))
  const defaultUrl = selectedUrls.includes(choice.defaultUrl) ? choice.defaultUrl : selectedUrls[0] ?? null
  const change = (key, value) => setForm((previous) => ({ ...previous, [key]: value }))
  const changeShared = (key, value) => setShared((previous) => ({ ...previous, [key]: value }))
  const uploadDescriptionImage = async (file) => (await auth.withAccessToken((token) => uploadProductImage(token, file))).ImageUrl
  const lookupsError = commonEditable && (categories.error || brands.error)
  const blocked = commonEditable ? categories.loading || brands.loading || Boolean(lookupsError) : !item && (!parent.data || parent.loading || Boolean(parent.error))
  async function write(body) {
    if (writing.current || !auth.permissions.includes(item ? 'products:update' : 'products:create')) return
    writing.current = true; setBusy(true); setError('')
    try {
      await auth.withAccessToken((token) => item ? editingShared ? updateCatalogProduct(token, item.ProductId, body) : updateCatalogItem(token, item.ProductVariantId, body) : createCatalogItem(token, body))
      if (mounted.current) onDone(item ? editingShared ? 'Đã cập nhật thông tin chung cho các biến thể của sản phẩm.' : 'Đã cập nhật biến thể.' : newProduct ? 'Đã tạo sản phẩm và biến thể đầu tiên.' : 'Đã thêm biến thể vào sản phẩm.')
    } catch (failure) { if (mounted.current) { setError(failure.message); setPending(null) } }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  function submit(event) {
    event.preventDefault()
    if (busy || uploading || blocked) return
    let body
    try {
      if (editingShared) body = sharedBody(shared)
      else {
        if (!form.Sku.trim() || !form.Color.trim()) throw new Error('Vui lòng nhập SKU và một màu sắc.')
        body = { ...form, Sku: form.Sku.trim(), Color: form.Color.trim(), Storage: form.Storage.trim() || null, Price: String(form.Price), MinStockLevel: Number(form.MinStockLevel) }
        body.VariantImageUrls = selectedUrls
        body.DefaultImageUrl = defaultUrl
        body.IsDefaultVariant = newProduct || makeDefault
        if (!newProduct) body.AdditionalImages = gallery.filter((image) => !originalImages.some((original) => original.ImageUrl === image.ImageUrl)).map(({ ImageUrl }) => ({ ImageUrl }))
        if (newProduct) body.Product = sharedBody(shared)
        else if (!item) { if (!parent.data || parent.error || parent.loading) throw new Error('Vui lòng chọn sản phẩm đã có.'); body.ProductId = parentId }
      }
      setError('')
      if (item) setPending(body)
      else void write(body)
    } catch (failure) { setError(failure.message) }
  }
  return <section className="-mt-0.5 flex min-w-0 flex-col gap-5" aria-label={item ? 'Cập nhật sản phẩm' : 'Thêm sản phẩm'}>
    <h2 className="m-0 text-xl leading-6 font-bold">{item ? 'Cập nhật thông tin sản phẩm' : 'Thêm sản phẩm mới'}</h2>
    <form onSubmit={submit} className="flex flex-col gap-5">
      {(error || lookupsError || parent.error) && <p role="alert" className="m-0 rounded-[10px] bg-admin-red/5 p-3 text-xs text-admin-red">{error || lookupsError || parent.error}</p>}
      {lookupsError && <ProductButton secondary onClick={() => { categories.refresh(); brands.refresh() }}>Thử lại danh mục / thương hiệu</ProductButton>}
      <fieldset disabled={busy || uploading || Boolean(pending)} className="m-0 min-w-0 border-0 p-0">
        <div className="grid grid-cols-[minmax(0,1fr)_360px] items-start gap-5">
          <div className="flex min-w-0 flex-col gap-[18px]">
            <section className={CARD + ' flex flex-col gap-3.5'}><h3 className="m-0 text-[15px] font-semibold">Thông tin chung</h3>
              {!item && <div role="radiogroup" aria-label="Cách thêm sản phẩm" className="flex gap-4 text-xs"><label className="flex items-center gap-2"><input type="radio" name="product-target" checked={target === 'new'} onChange={() => setTarget('new')} />Sản phẩm mới</label><label className="flex items-center gap-2"><input type="radio" name="product-target" checked={target === 'existing'} onChange={() => setTarget('existing')} />Biến thể của sản phẩm đã có</label></div>}
              {!item && target === 'existing' && <ParentPicker value={parentId} onChange={setParentId} selected={parent.data} lookup={{ ...lookup, page, setPage, search: (value) => { setKeyword(value); setPage(1) } }} />}
              {item && <div className="flex gap-2 text-xs"><button type="button" className={'cursor-pointer rounded-lg px-3 py-2 ' + (!editingShared ? 'bg-admin-soft text-admin-blue' : 'bg-admin-page text-admin-muted')} onClick={() => { setEditingShared(false); setError('') }}>Sửa biến thể</button><button type="button" className={'cursor-pointer rounded-lg px-3 py-2 ' + (editingShared ? 'bg-admin-soft text-admin-blue' : 'bg-admin-page text-admin-muted')} onClick={() => { setEditingShared(true); setError('') }}>Sửa thông tin chung</button></div>}
              <div className="flex w-full max-w-[520px] flex-col gap-3.5">
                {!editingShared && <label className="flex items-center gap-2 text-xs"><input type="checkbox" aria-label="Biến thể mặc định" checked={newProduct || makeDefault} disabled={newProduct || Boolean(item?.IsDefaultVariant)} onChange={(event) => setMakeDefault(event.target.checked)} />{newProduct ? 'Biến thể đầu tiên là biến thể mặc định' : 'Đặt làm biến thể mặc định của sản phẩm'}</label>}
                <ProductField id="product-name" label="Tên sản phẩm" required maxLength={255} disabled={!commonEditable} placeholder="Nhập tên sản phẩm" value={common.Name} onChange={(event) => changeShared('Name', event.target.value)} />
                <div className="grid grid-cols-2 gap-3.5"><ProductField id="product-sku" label="Mã sản phẩm (SKU)" required maxLength={50} disabled={editingShared} placeholder="Nhập SKU" value={form.Sku} onChange={(event) => change('Sku', event.target.value)} />{commonEditable ? <ProductSelect id="product-status" label="Trạng thái sản phẩm" options={PRODUCT_STATUSES} required value={common.Status} onChange={(event) => changeShared('Status', event.target.value)} /> : <ProductSelect id="variant-status" label="Trạng thái biến thể" options={[["true", 'Hoạt động'], ["false", 'Tạm ẩn']]} value={String(form.IsActive)} onChange={(event) => change('IsActive', event.target.value === 'true')} />}</div>
                <div className="grid grid-cols-2 gap-3.5"><ProductSelect id="product-category" label="Danh mục" options={(categories.data ?? []).map((entry) => [entry.CategoryId, entry.Name + (entry.IsActive ? '' : ' (đã ẩn)')])} required disabled={!commonEditable || categories.loading} value={common.CategoryId} onChange={(event) => changeShared('CategoryId', event.target.value)} /><ProductSelect id="product-brand" label="Thương hiệu" options={(brands.data ?? []).map((entry) => [entry.BrandId, entry.Name + (entry.IsActive ? '' : ' (đã ẩn)')])} required disabled={!commonEditable || brands.loading} value={common.BrandId} onChange={(event) => changeShared('BrandId', event.target.value)} /></div>
              </div>
              <RichTextEditor id="product-description" label="Mô tả" labelClassName="text-xs font-medium" readOnly={!commonEditable} disabled={busy || uploading || Boolean(pending)} value={common.Description} onChange={(value) => changeShared('Description', value)} onUploadImage={uploadDescriptionImage} onUploadBusy={setUploading} />
              <div className="grid w-full max-w-[520px] grid-cols-2 gap-3.5"><ProductField id="product-color" label="Màu sắc" required maxLength={50} disabled={editingShared} placeholder="Một màu cho mỗi biến thể" value={form.Color} onChange={(event) => change('Color', event.target.value)} /><ProductField id="product-storage" label="Dung lượng" maxLength={50} disabled={editingShared} value={form.Storage} onChange={(event) => change('Storage', event.target.value)} /></div>
              <details className="text-xs"><summary className="cursor-pointer text-admin-blue">Thông tin bổ sung</summary><div className="mt-3 flex max-w-[520px] flex-col gap-3.5"><ProductField id="product-warranty" label="Bảo hành (tháng)" type="number" required min={0} step={1} disabled={!commonEditable} value={common.WarrantyMonths} onChange={(event) => changeShared('WarrantyMonths', event.target.value)} /><ProductField id="product-specifications" label="Thông số kỹ thuật (JSON)"><textarea id="product-specifications" rows={3} className={CONTROL + ' h-auto py-3 font-mono'} disabled={!commonEditable} placeholder={'{"RAM":"16GB"}'} value={common.Specifications} onChange={(event) => changeShared('Specifications', event.target.value)} /></ProductField></div></details>
            </section>
            {!editingShared && <VariantImageSelection images={gallery} selected={selectedUrls} defaultUrl={defaultUrl} sku={form.Sku} color={form.Color} onChange={(urls, selectedDefault) => setSelections((previous) => ({ ...previous, [galleryKey]: { urls, defaultUrl: selectedDefault } }))} />}
            <section className={CARD + ' flex flex-col gap-3.5'}><h3 className="m-0 text-[15px] font-semibold">Giá và tồn kho</h3><div className="grid max-w-[520px] grid-cols-2 gap-3.5"><ProductField id="product-price" label="Giá bán (đồng)" type="number" required min={0} max="9999999999999.99" step="0.01" placeholder="Nhập giá bán" disabled={editingShared} value={form.Price} onChange={(event) => change('Price', event.target.value)} /><ProductField id="product-stock" label="Số lượng tồn kho" type="number" readOnly value={item?.StockQuantity ?? 0} /></div><p className="m-0 text-[11px] text-admin-muted">Tồn kho được cập nhật qua nhập hàng; biến thể mới có tồn kho bằng 0.</p><details className="text-xs"><summary className="cursor-pointer text-admin-blue">Thiết lập biến thể</summary><div className="mt-3 flex max-w-[520px] flex-col gap-3"><ProductField id="product-min" label="Ngưỡng cảnh báo tồn" type="number" min={0} step={1} required disabled={editingShared} value={form.MinStockLevel} onChange={(event) => change('MinStockLevel', event.target.value)} /><label className="flex gap-2"><input type="checkbox" disabled={editingShared} checked={form.IsActive} onChange={(event) => change('IsActive', event.target.checked)} />Đang hoạt động</label><label className="flex gap-2"><input type="checkbox" disabled={editingShared} checked={form.IsSerialTracked} onChange={(event) => change('IsSerialTracked', event.target.checked)} />Quản lý Serial / IMEI</label></div></details></section>
          </div>
          <aside className="flex min-w-0 flex-col gap-[18px]"><AdminImagePicker title="Bộ ảnh sản phẩm" images={gallery} onChange={(images) => commonEditable ? changeShared('Images', images) : setGalleries((previous) => ({ ...previous, [galleryKey]: images }))} disabled={busy || uploading || Boolean(pending) || (!item && !newProduct && !parent.data)} onUploadBusy={setUploading} showDefault={commonEditable} canRemove={(image) => commonEditable || !originalImages.some((original) => original.ImageUrl === image.ImageUrl)} hint={editingShared ? 'Quản lý bộ ảnh chung. Bỏ ảnh ở đây cũng bỏ ảnh đó khỏi các biến thể đang dùng.' : 'Ảnh tải từ máy được đưa vào bộ ảnh Product. Chọn ảnh cho SKU ở mục “Ảnh của biến thể”.'} /><div className={CARD + ' flex flex-col gap-2 p-[18px]'}><h3 className="m-0 text-sm font-semibold">{item ? 'Lưu ý xử lý' : 'Lưu ý khi thêm mới'}</h3><p className="m-0 text-[11px] leading-normal text-admin-muted">{editingShared ? 'Thay đổi tên, danh mục, thương hiệu, mô tả, bảo hành, trạng thái và bộ ảnh áp dụng cho sản phẩm chung.' : item ? 'SKU, màu sắc, dung lượng, giá và ảnh đã chọn chỉ áp dụng cho biến thể này. Thông tin chung được chỉnh ở “Sửa thông tin chung”.' : 'Mỗi biến thể có một SKU, một màu sắc và những ảnh được chọn từ bộ ảnh Product. Biến thể đầu tiên là mặc định.'}</p></div></aside>
        </div>
      </fieldset>
      <footer className="flex items-center gap-2.5"><p className="m-0 flex-1 text-[11px] text-admin-muted">{item ? 'Thay đổi được lưu sau khi bạn xác nhận.' : 'Sản phẩm chỉ được tạo sau khi bấm “Thêm sản phẩm”.'}</p><ProductButton secondary className="text-admin-text!" disabled={busy || uploading} onClick={onClose}>Hủy</ProductButton><ProductButton type="submit" loading={busy} disabled={uploading || blocked || Boolean(pending)}>{item ? 'Lưu thay đổi' : 'Thêm sản phẩm'}</ProductButton></footer>
    </form>
    {pending && <Modal open variant="product-save" className="w-[366px] min-h-[177px]" title="Xác nhận những thay đổi?" busy={busy} onClose={() => setPending(null)}><div className="flex justify-center gap-[43px]"><Button variant="secondary" className="h-[42px]! w-[100px] rounded-[9px]! border-[#dbe3ed]! bg-white! px-0! font-admin! text-sm text-admin-red!" disabled={busy} onClick={() => setPending(null)}>Hủy</Button><Button className="h-[42px]! w-[100px] rounded-[9px]! border-0 bg-admin-red! px-0! font-admin! text-sm text-white" loading={busy} onClick={() => void write(pending)}>Xác nhận</Button></div></Modal>}
  </section>
}

export default function ProductWorkspace({ mode, variantId, productId, editShared, categories, brands, onClose, onDone, onEdit, onEditShared, onAddVariant, onNew }) {
  const detail = useAdminQuery('/admin/catalog-items/' + encodeURIComponent(variantId ?? ''), {}, mode !== 'new')
  if (mode !== 'new' && detail.loading) return <LoadingState label="Đang tải sản phẩm…" />
  if (mode !== 'new' && detail.error) return <><ProductButton secondary onClick={onClose}>Quay lại</ProductButton><ErrorState message={detail.error} onRetry={detail.refresh} /></>
  if (mode !== 'new' && !detail.data) return <p role="status">Không tìm thấy sản phẩm. <ProductButton secondary onClick={onClose}>Quay lại</ProductButton></p>
  if (mode === 'view') return <ProductDetailsPage item={detail.data} onClose={onClose} onDone={onDone} onEdit={onEdit} onEditShared={onEditShared} onAddVariant={onAddVariant} onNew={onNew} />
  return <ProductFormPage item={mode === 'edit' ? detail.data : null} presetProductId={productId} editShared={editShared} categories={categories} brands={brands} onClose={onClose} onDone={onDone} />
}
