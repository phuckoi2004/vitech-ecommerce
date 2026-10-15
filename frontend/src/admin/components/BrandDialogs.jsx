import { useState } from 'react'
import Field from '../../components/shared/Field.jsx'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { slugFromName } from '../../lib/admin-products.js'
import { validLogoUrl } from '../lib/brands.js'
import { createBrand, deleteBrand, updateBrand } from '../services/brands.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import Modal from './Modal.jsx'
import { PRODUCT_CONTROL, ProductButton } from './ProductUi.jsx'
import AdminImagePicker from './AdminImagePicker.jsx'

function BrandError({ message }) {
  return message ? <p role="alert" className="mb-4 rounded-[10px] bg-admin-red/5 p-3 text-sm text-admin-red">{message}</p> : null
}

function BrandLogo({ name, url }) {
  const [failed, setFailed] = useState(false)
  if (!url) return <p className="text-xs text-admin-muted">Chưa có logo.</p>
  if (!validLogoUrl(url) || failed) return <p className="text-xs text-admin-muted">Không tải được logo.</p>
  return <img src={url} alt={'Logo ' + name} width={192} height={96} className="h-24 w-48 rounded-lg border border-admin-border bg-white p-3 object-contain" onError={() => setFailed(true)} />
}

function BrandEditor({ brand, onBusy, onClose, onDone }) {
  const auth = useInternalAuth()
  const [form, setForm] = useState(() => ({ Name: brand?.Name ?? '', Slug: brand?.Slug ?? '', Description: brand?.Description ?? '', LogoUrl: brand?.LogoUrl ?? '', IsActive: brand?.IsActive ?? true }))
  const [slugEdited, setSlugEdited] = useState(Boolean(brand))
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  function change(key, value) {
    setForm((previous) => ({ ...previous, [key]: value, ...(key === 'Name' && !slugEdited ? { Slug: slugFromName(value) } : {}) }))
    if (key === 'Slug') setSlugEdited(true)
    setError('')
  }
  async function save(event) {
    event.preventDefault()
    if (busy || uploading) return
    if (!form.Name.trim()) { setError('Tên thương hiệu không được để trống.'); return }
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.Slug.trim())) { setError('Đường dẫn chỉ gồm chữ thường không dấu, số và dấu gạch ngang.'); return }
    if (form.LogoUrl.trim() && !validLogoUrl(form.LogoUrl.trim())) { setError('Ảnh logo chưa hợp lệ. Vui lòng chọn lại ảnh từ máy.'); return }
    const body = { ...form, Name: form.Name.trim(), Slug: form.Slug.trim(), Description: form.Description.trim() || null, LogoUrl: form.LogoUrl.trim() || null }
    setError(''); setBusy(true); onBusy(true)
    try {
      await auth.withAccessToken((token) => brand ? updateBrand(token, brand.BrandId, body) : createBrand(token, body))
      onDone(brand ? 'Đã cập nhật thương hiệu.' : 'Đã thêm thương hiệu.')
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false); onBusy(false) }
  }
  return <form onSubmit={save}>
    <BrandError message={error} />
    <fieldset disabled={busy || uploading} className="grid min-w-0 grid-cols-2 gap-4 border-0 p-0">
      <Field id="brand-name" label="Tên thương hiệu" className="col-span-full" required maxLength={255} value={form.Name} onChange={(event) => change('Name', event.target.value)} />
      <Field id="brand-slug" label="Đường dẫn (slug)" className="col-span-full" required maxLength={300} pattern="[a-z0-9]+(-[a-z0-9]+)*" hint="Được gợi ý từ tên thương hiệu; bạn có thể chỉnh lại." value={form.Slug} onChange={(event) => change('Slug', event.target.value)} />
      <Field id="brand-description" label="Mô tả" className="col-span-full"><textarea id="brand-description" className={PRODUCT_CONTROL} rows={4} value={form.Description} onChange={(event) => change('Description', event.target.value)} /></Field>
      <div className="col-span-full"><AdminImagePicker title="Logo thương hiệu" name="logo thương hiệu" multiple={false} images={form.LogoUrl ? [{ ImageUrl: form.LogoUrl, IsDefault: true }] : []} onChange={(images) => change('LogoUrl', images[0]?.ImageUrl ?? '')} onUploadBusy={(value) => { setUploading(value); onBusy(value) }} /></div>
      <Field id="brand-status" label="Trạng thái" className="col-span-full"><select id="brand-status" className={PRODUCT_CONTROL} value={form.IsActive ? 'active' : 'hidden'} onChange={(event) => change('IsActive', event.target.value === 'active')}>
        <option value="active">Đang hiển thị</option><option value="hidden">Đã ẩn</option>
      </select></Field>
    </fieldset>
    <div className="mt-5 flex justify-end gap-2"><ProductButton secondary disabled={busy || uploading} onClick={onClose}>Hủy</ProductButton><ProductButton type="submit" loading={busy} disabled={uploading}>{brand ? 'Lưu thay đổi' : 'Thêm thương hiệu'}</ProductButton></div>
  </form>
}

function BrandDetails({ brand, onEdit, onClose }) {
  const auth = useInternalAuth()
  return <>
    <h3 className="mb-5 break-words text-lg font-semibold">{brand.Name}</h3>
    <dl className="grid grid-cols-2 gap-5">{[['Đường dẫn', brand.Slug], ['Trạng thái', brand.IsActive ? 'Đang hiển thị' : 'Đã ẩn']].map(([label, value]) => <div key={label}><dt className="text-xs text-admin-muted">{label}</dt><dd className="mt-1 break-words text-sm">{value}</dd></div>)}</dl>
    <h4 className="mt-5 text-xs text-admin-muted">Mô tả</h4><p className="mt-1 text-sm whitespace-pre-wrap">{brand.Description || 'Chưa có mô tả.'}</p>
    <h4 className="mt-5 mb-2 text-xs text-admin-muted">Logo</h4><BrandLogo key={brand.LogoUrl} name={brand.Name} url={brand.LogoUrl} />
    <div className="mt-6 flex justify-end gap-2"><ProductButton secondary onClick={onClose}>Đóng</ProductButton>{auth.permissions.includes('brands:update') && <ProductButton onClick={onEdit}>Sửa thương hiệu</ProductButton>}</div>
  </>
}

function BrandDelete({ brand, onBusy, onClose, onDone }) {
  const auth = useInternalAuth()
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState(null)
  async function remove(hide = false) {
    if (busy) return
    setBusy(true); onBusy(true); setFailure(null)
    try {
      await auth.withAccessToken((token) => hide ? updateBrand(token, brand.BrandId, { IsActive: false }) : deleteBrand(token, brand.BrandId))
      onDone(hide ? 'Đã ẩn thương hiệu.' : 'Đã xóa thương hiệu.')
    } catch (error) { setFailure(error) }
    finally { setBusy(false); onBusy(false) }
  }
  return <>
    <BrandError message={failure?.message} />
    <p>Bạn muốn xóa thương hiệu <strong className="break-words">{brand.Name}</strong>?</p>
    <p className="mt-3 text-xs leading-relaxed text-admin-muted">Chỉ xóa được thương hiệu không còn sản phẩm liên quan. Nếu muốn tạm ngừng hiển thị, hãy đổi trạng thái thành “Đã ẩn”.</p>
    <div className="mt-6 flex justify-end gap-2"><ProductButton secondary disabled={busy} onClick={onClose}>Hủy</ProductButton>
      {failure?.code === 'brand_has_products' && brand.IsActive && auth.permissions.includes('brands:update') && <ProductButton secondary disabled={busy} onClick={() => remove(true)}>Ẩn thương hiệu</ProductButton>}
      <ProductButton loading={busy} className="border-admin-red! bg-admin-red! enabled:hover:bg-admin-red/90!" onClick={() => remove()}>Xác nhận xóa</ProductButton>
    </div>
  </>
}

export default function BrandDialog({ mode, brandId, onClose, onDone, onEdit }) {
  const detail = useAdminQuery('/brands/' + encodeURIComponent(brandId ?? ''), { active_only: false }, mode !== 'new')
  const [busy, setBusy] = useState(false)
  const title = { new: 'Thêm thương hiệu', edit: 'Sửa thương hiệu', view: 'Chi tiết thương hiệu', delete: 'Xóa thương hiệu' }[mode]
  return <Modal variant="tailwind" open wide={mode !== 'delete'} title={title} busy={busy} onClose={onClose}>
    {mode !== 'new' && detail.loading ? <LoadingState label="Đang tải thương hiệu…" /> : mode !== 'new' && detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} /> : mode === 'view' && detail.data ? <BrandDetails brand={detail.data} onClose={onClose} onEdit={onEdit} /> : mode === 'delete' && detail.data ? <BrandDelete brand={detail.data} onBusy={setBusy} onClose={onClose} onDone={onDone} /> : (mode === 'new' || detail.data) ? <BrandEditor brand={detail.data} onBusy={setBusy} onClose={onClose} onDone={onDone} /> : null}
  </Modal>
}
