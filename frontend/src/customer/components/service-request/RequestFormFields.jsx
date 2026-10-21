import { useRef, useState } from 'react'
import { AVATAR_MAX_BYTES, AVATAR_TYPES } from '../../../lib/account-api.js'
import StoreImage from '../StoreImage.jsx'
import { lineDisplay } from '../cart/cartLines.js'
import useProductDetails from '../cart/useProductDetails.js'

export function RequestField({ id, label, children }) {
  return <div className="cacc-field"><label htmlFor={id} className="cw-label">{label}</label>{children}</div>
}

export function RequestProduct({ item, orderCode, badge = 'CHỜ KIỂM TRA', subtitle = 'Sản phẩm mua tại VieTech' }) {
  const details = useProductDetails([item.ProductId])
  const display = lineDisplay(item, details[item.ProductId])
  return <div className="cw-product">
    <StoreImage src={display.imageUrl} alt={item.ProductName} fallback={<span className="cw-product-placeholder" aria-label="Chưa có ảnh sản phẩm">Chưa có ảnh</span>} />
    <div><strong>{item.ProductName}</strong><p>{item.VariantInfo}</p><p>Mã đơn: {orderCode} · Số lượng: {item.Quantity}</p><span>{subtitle}</span></div>
    <div className="cw-product-badge"><strong>{badge}</strong><p>Điều kiện thực tế sau tiếp nhận</p></div>
  </div>
}

export function EvidenceImages({ entries, setEntries, busy, setBusy, withAccessToken, uploadImage }) {
  const input = useRef(null)
  const lock = useRef(false)
  const [error, setError] = useState('')

  async function upload(entriesToUpload) {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    try {
      for (const entry of entriesToUpload) {
        setEntries((current) => current.map((row) => row.id === entry.id ? { ...row, error: '', uploading: true } : row))
        try {
          const attachment = await withAccessToken((token) => uploadImage(token, entry.file))
          setEntries((current) => current.map((row) => row.id === entry.id ? { ...row, attachment, uploading: false } : row))
        } catch (failure) {
          setEntries((current) => current.map((row) => row.id === entry.id ? { ...row, error: failure.message, uploading: false } : row))
        }
      }
    } finally {
      lock.current = false
      setBusy(false)
    }
  }

  function pick(event) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    setError('')
    if (entries.length + files.length > 5) return setError('Bạn có thể đính kèm tối đa 5 ảnh.')
    if (files.some((file) => !AVATAR_TYPES.includes(file.type) || file.size > AVATAR_MAX_BYTES || file.size === 0)) {
      return setError('Chọn ảnh JPG, PNG hoặc WEBP, mỗi ảnh tối đa 2 MB và không rỗng.')
    }
    const next = files.map((file) => ({ id: crypto.randomUUID(), file, uploading: true }))
    setEntries((current) => [...current, ...next])
    void upload(next)
  }

  return <>
    <input ref={input} type="file" accept={AVATAR_TYPES.join(',')} multiple hidden onChange={pick} disabled={busy} aria-label="Chọn ảnh minh chứng" />
    <button type="button" className="cw-upload" onClick={() => input.current.click()} disabled={busy || entries.length >= 5}>
      <span aria-hidden="true">↥</span><strong>{busy ? 'Đang tải ảnh lên…' : 'Nhấn để tải ảnh tình trạng lỗi sản phẩm'}</strong>
      <small>JPG, PNG, WEBP · Tối đa 5 ảnh, mỗi ảnh 2 MB</small>
    </button>
    {error && <p className="cacc-notice" role="alert">{error}</p>}
    {entries.length > 0 && <ul className="cw-evidence" aria-label="Ảnh minh chứng đã chọn">
      {entries.map((entry) => <li key={entry.id}>
        {entry.attachment && <img src={entry.attachment.FileUrl} alt={`Minh chứng: ${entry.file.name}`} />}
        <div><strong>{entry.file.name}</strong><p role={entry.error ? 'alert' : 'status'}>{entry.error || (entry.uploading ? 'Đang tải lên…' : 'Đã tải lên')}</p></div>
        {entry.error && <button type="button" disabled={busy} className="cw-text-button" onClick={() => upload([entry])}>Tải lại</button>}
        <button type="button" disabled={busy} className="cw-text-button" aria-label={`Xóa ảnh ${entry.file.name}`}
          onClick={() => setEntries((current) => current.filter((row) => row.id !== entry.id))}>Xóa</button>
      </li>)}
    </ul>}
    <p className="cw-help"><strong>Gợi ý:</strong> Chụp rõ Serial/IMEI và tình trạng lỗi để quá trình tiếp nhận nhanh hơn.</p>
  </>
}

