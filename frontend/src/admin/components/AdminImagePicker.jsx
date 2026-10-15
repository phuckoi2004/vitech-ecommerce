import { useEffect, useId, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { uploadProductImage } from '../services/product-media.js'
import { ProductButton } from './ProductUi.jsx'

// Only server-returned URLs enter the draft. Admins choose local files, never enter image URLs.
export default function AdminImagePicker({ images, onChange, name = 'sản phẩm', title = 'Hình ảnh sản phẩm', hint, disabled = false, multiple = true, onUploadBusy, showDefault = true, canRemove = () => true, variant }) {
  const auth = useInternalAuth(), input = useRef(null), writing = useRef(false), mounted = useRef(true)
  const groupId = useId()
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [progress, setProgress] = useState('')
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const unavailable = disabled || busy
  async function upload(files) {
    if (unavailable || writing.current || !files?.length) return
    const batch = multiple ? [...files] : [...files].slice(0, 1)
    if (batch.some((file) => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || !file.size || file.size > 2 * 1024 * 1024)) { setError('Chọn ảnh JPG, PNG hoặc WEBP, tối đa 2 MB mỗi ảnh.'); return }
    writing.current = true; setBusy(true); setError(''); onUploadBusy?.(true)
    const savedImages = multiple ? [...images] : []
    try {
      for (const [index, file] of batch.entries()) {
        if (!mounted.current) break
        setProgress(`Đang tải ảnh ${index + 1}/${batch.length}…`)
        const result = await auth.withAccessToken((token) => uploadProductImage(token, file))
        if (!result?.ImageUrl) throw new Error('Máy chủ chưa trả về ảnh đã tải lên. Vui lòng thử lại.')
        if (mounted.current) {
          savedImages.push({ ImageUrl: result.ImageUrl, IsDefault: !savedImages.length })
          onChange([...savedImages])
        }
      }
    } catch (failure) { if (mounted.current) setError(failure.message) }
    finally { writing.current = false; if (mounted.current) { setBusy(false); setProgress(''); onUploadBusy?.(false); if (input.current) input.current.value = '' } }
  }
  function remove(index) {
    const remaining = images.filter((_, i) => i !== index)
    if (remaining.length && !remaining.some((image) => image.IsDefault)) remaining[0] = { ...remaining[0], IsDefault: true }
    onChange(remaining)
  }
  const fileInput = <input ref={input} className="sr-only" type="file" aria-label={'Tải ảnh ' + name} accept="image/jpeg,image/png,image/webp" multiple={multiple} disabled={unavailable} onChange={(event) => void upload(event.target.files)} />
  if (['news', 'compact'].includes(variant)) return <section aria-label={title} className="flex min-w-0 flex-col gap-[5px]">
    <h3 className="m-0 text-[9px] leading-[11px] font-medium text-admin-muted">{title}</h3>
    <div className="flex h-[38px] items-center gap-2 rounded-lg border border-admin-border bg-white px-2.5" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void upload(event.dataTransfer.files) }}>
      {images[0] && <img src={images[0].ImageUrl} alt={variant === 'news' ? 'Ảnh đại diện tin tức' : 'Ảnh ' + name} className="h-[30px] w-12 shrink-0 rounded object-contain" />}
      <button type="button" disabled={unavailable} onClick={() => input.current?.click()} className="flex-1 cursor-pointer border-0 bg-transparent p-0 text-left text-[9px] text-admin-text disabled:cursor-wait disabled:opacity-50">{busy ? progress : images.length ? 'Thay ảnh từ máy' : 'Chọn ảnh từ máy (JPG, PNG, WEBP; tối đa 2 MB)'}</button>
      {images[0] && canRemove(images[0]) && <button type="button" disabled={unavailable} onClick={() => remove(0)} className="cursor-pointer text-[9px] text-admin-red disabled:opacity-50" aria-label={variant === 'news' ? 'Bỏ ảnh đại diện' : 'Bỏ ảnh ' + name}>Bỏ ảnh</button>}
      {fileInput}
    </div>
    {error && <p role="alert" className="m-0 text-[10px] text-admin-red">{error}</p>}
  </section>
  return <section aria-label={title} className="flex min-w-0 flex-col gap-3.5 rounded-[14px] border border-admin-border bg-white p-5">
    <h3 className="m-0 text-[15px] font-semibold">{title}</h3>
    <div className="flex min-h-[150px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-admin-border bg-admin-page p-4" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void upload(event.dataTransfer.files) }}>
      {!images.length && <p className="m-0 text-[13px] font-semibold text-admin-muted">Chưa có ảnh {name}</p>}
      {!disabled && <ProductButton secondary disabled={busy} onClick={() => input.current?.click()}>{images.length ? multiple ? '+ Thêm ảnh' : 'Thay ảnh từ máy' : 'Chọn ảnh từ máy'}</ProductButton>}
      {!disabled && <p className="m-0 text-[11px] text-admin-muted">Hoặc kéo thả ảnh vào đây. JPG, PNG, WEBP; tối đa 2 MB mỗi ảnh.</p>}
      {progress && <p role="status" className="m-0 text-xs text-admin-muted">{progress}</p>}
      {fileInput}
    </div>
    {error && <p role="alert" className="m-0 text-xs text-admin-red">{error}</p>}
    {hint && <p className="m-0 text-[11px] leading-normal text-admin-muted">{hint}</p>}
    <div className="grid grid-cols-2 gap-3">{images.map((image, index) => <div key={image.ImageUrl + '-' + index} className="flex min-w-0 flex-col gap-2 rounded-lg border border-admin-border p-2">
      <img src={image.ImageUrl} alt={'Ảnh ' + name + ' ' + (index + 1)} className="h-24 w-full rounded-md bg-admin-page object-contain" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        {multiple && showDefault ? <label className="flex items-center gap-1.5 text-[11px]"><input type="radio" name={'default-image-' + groupId} aria-label={'Ảnh mặc định ' + (index + 1)} checked={image.IsDefault} disabled={unavailable} onChange={() => onChange(images.map((entry, i) => ({ ...entry, IsDefault: i === index })))} />Mặc định</label> : <span className="text-[11px] text-admin-muted">Ảnh {index + 1}</span>}
        {canRemove(image) && <button type="button" aria-label={'Bỏ ảnh ' + (index + 1)} disabled={unavailable} className="cursor-pointer text-[11px] text-admin-red disabled:opacity-40" onClick={() => remove(index)}>Bỏ ảnh</button>}
      </div>
    </div>)}</div>
  </section>
}
