import { useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { setStockQuantity } from '../services/inventory.js'
import Modal from './Modal.jsx'
import { PRODUCT_CONTROL, ProductButton } from './ProductUi.jsx'

const MAX_STOCK = 2147483647

export default function ProductStockDialog({ item, onClose, onSaved, onRefresh, inline = false, onDirtyChange, onBusyChange, serialTracking, onResetTracking }) {
  const auth = useInternalAuth()
  const permitted = auth.user?.Role === 'Admin' && auth.permissions.includes('inventory:update')
  const [quantity, setQuantity] = useState(String(item.StockQuantity))
  const [serialStep, setSerialStep] = useState(false), [serialText, setSerialText] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [uncertain, setUncertain] = useState(false)
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const value = Number(quantity)
  const tracking = serialTracking ?? item.IsSerialTracked
  const trackingChanged = tracking !== item.IsSerialTracked
  const unchanged = value === item.StockQuantity && !trackingChanged
  const invalid = !quantity.trim() || !Number.isSafeInteger(value) || value < 0 || value > MAX_STOCK
  function changeQuantity(next) {
    setQuantity(next)
    onDirtyChange?.(!next.trim() || Number(next) !== item.StockQuantity)
  }
  function stepQuantity(change) {
    if (writing.current || busy || invalid || serialStep) return
    changeQuantity(String(Math.max(0, Math.min(MAX_STOCK, value + change))))
  }
  function close() {
    if (writing.current) return
    if (uncertain) onRefresh()
    onDirtyChange?.(false)
    if (inline) {
      onResetTracking?.()
      setQuantity(String(item.StockQuantity)); setSerialStep(false); setSerialText(''); setError(''); setUncertain(false)
    } else onClose()
  }
  async function save(event) {
    event.preventDefault()
    if (!permitted || invalid || unchanged || uncertain || writing.current) return
    let numbers
    if (tracking && value > item.StockQuantity) {
      if (!serialStep) { setError(''); setSerialStep(true); return }
      numbers = serialText.split(/[\n,;]+/).map(number => number.trim()).filter(Boolean)
      if (numbers.length !== value - item.StockQuantity) { setError('Phải nhập đúng ' + (value - item.StockQuantity) + ' Serial/IMEI.'); return }
      if (new Set(numbers).size !== numbers.length || numbers.some(number => number.length > 100)) { setError('Serial/IMEI bị trùng hoặc vượt quá 100 ký tự.'); return }
    }
    writing.current = true; setBusy(true); setError('')
    onBusyChange?.(true)
    try {
      const result = await auth.withAccessToken(token => setStockQuantity(token, item.ProductVariantId, {
        StockQuantity: value, ExpectedStockQuantity: item.StockQuantity,
        ...(numbers ? { SerialNumbers: numbers } : {}),
        ...(trackingChanged ? { IsSerialTracked: tracking, ExpectedIsSerialTracked: item.IsSerialTracked } : {}),
      }))
      if (mounted.current) {
        onDirtyChange?.(false)
        if (inline) setSerialStep(false)
        window.dispatchEvent(new Event('admin-order-updated'))
        onSaved({ QuantityBefore: item.StockQuantity, QuantityAfter: result.StockQuantity,
          ...(typeof result.IsSerialTracked === 'boolean' || trackingChanged ? { IsSerialTracked: result.IsSerialTracked ?? tracking } : {}),
        })
      }
    } catch (failure) {
      if (mounted.current) {
        setError(failure.message || 'Không thể cập nhật tồn kho.')
        if (!failure.status || failure.status >= 500 || (failure.status === 409 && failure.code !== 'serial_exists')) setUncertain(true)
      }
    } finally {
      writing.current = false
      if (mounted.current) { setBusy(false); onBusyChange?.(false) }
    }
  }
  if (!permitted) return null
  const embedded = inline && !serialStep
  const content = <>
      {!embedded && <p className="m-0 text-xs text-admin-muted">{serialStep ? 'Cần nhập ' + (value - item.StockQuantity) + ' mã thực tế cho số lượng tăng thêm. Mỗi mã một dòng.' : <>Tồn kho hiện tại: <strong>{item.StockQuantity}</strong>. Nhập số lượng tồn kho mới, có thể bằng 0.</>}</p>}
      {error && <p role="alert" className="m-0 text-xs text-admin-red">{error}</p>}
      {uncertain ? <p className="m-0 text-xs text-amber-700">Cần tải lại chi tiết để kiểm tra số tồn hiện tại trước khi sửa tiếp.</p> : <>
        {serialStep ? <label className="flex flex-col gap-1.5 text-xs font-medium">Serial/IMEI<textarea aria-label="Serial/IMEI" className={PRODUCT_CONTROL + ' min-h-40'} required disabled={busy} placeholder="Mỗi máy một mã, mỗi mã một dòng" value={serialText} onChange={(event) => setSerialText(event.target.value)} /></label> : <div className="flex flex-col gap-1.5 text-xs font-medium">
          <label htmlFor="stock-quantity-input">{embedded ? 'Số lượng tồn kho' : 'Số lượng tồn kho mới'}</label>
          <div className="relative">
            <input id="stock-quantity-input" className={PRODUCT_CONTROL + ' h-11 pr-12 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'} type="number" min="0" max={MAX_STOCK} step="1" required disabled={busy} value={quantity} onChange={(event) => changeQuantity(event.target.value)} onKeyDown={(event) => { if (embedded && event.key === 'Enter') { event.stopPropagation(); void save(event) } }} />
            <div className="absolute inset-y-1 right-1 flex w-8 flex-col divide-y divide-admin-border">
              <button type="button" aria-label="Tăng tồn kho 1" title="Tăng 1" className="flex flex-1 cursor-pointer items-center justify-center rounded-t-md border-0 bg-transparent text-[10px] text-black hover:bg-admin-soft focus-visible:outline-2 focus-visible:outline-admin-blue disabled:cursor-default disabled:opacity-30" disabled={busy || invalid || value >= MAX_STOCK} onClick={() => stepQuantity(1)}><span aria-hidden="true">▲</span></button>
              <button type="button" aria-label="Giảm tồn kho 1" title="Giảm 1" className="flex flex-1 cursor-pointer items-center justify-center rounded-b-md border-0 bg-transparent text-[10px] text-black hover:bg-admin-soft focus-visible:outline-2 focus-visible:outline-admin-blue disabled:cursor-default disabled:opacity-30" disabled={busy || invalid || value <= 0} onClick={() => stepQuantity(-1)}><span aria-hidden="true">▼</span></button>
            </div>
          </div>
        </div>}
        {invalid && <p role="alert" className="m-0 text-xs text-admin-red">Số lượng tồn kho phải là số nguyên từ 0 đến {MAX_STOCK.toLocaleString('vi-VN')}.</p>}
      </>}
      <div className="flex flex-wrap justify-end gap-2">{serialStep && !uncertain && <ProductButton secondary disabled={busy} onClick={() => { setSerialStep(false); setError('') }}>Quay lại</ProductButton>}{(!embedded || uncertain || !unchanged) && <ProductButton secondary disabled={busy} onClick={close}>{uncertain ? 'Đóng và tải lại' : embedded ? 'Hủy đổi tồn kho' : 'Hủy'}</ProductButton>}{!uncertain && <ProductButton type={inline ? 'button' : 'submit'} onClick={inline ? save : undefined} disabled={busy || invalid || unchanged}>{busy ? 'Đang lưu…' : serialStep ? 'Xác nhận sửa' : 'Lưu tồn kho'}</ProductButton>}</div>
  </>
  if (embedded) return <div className="flex min-w-0 flex-col gap-3" aria-label="Điều chỉnh tồn kho">{content}</div>
  return <Modal open variant="tailwind" title={serialStep ? 'Nhập Serial/IMEI cho hàng thêm mới' : 'Sửa số lượng tồn kho'} description={item.Name + ' — SKU: ' + item.Sku} busy={busy} onClose={close}>{inline ? <div className="flex flex-col gap-4">{content}</div> : <form onSubmit={save} className="flex flex-col gap-4">{content}</form>}</Modal>
}
