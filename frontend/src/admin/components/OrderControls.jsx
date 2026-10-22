import { useState } from 'react'
import { PRODUCT_CONTROL, ProductButton } from './ProductUi.jsx'

export function InternalNote({ order, busy, onSave }) {
  const [value, setValue] = useState(order.InternalNote ?? '')
  return <form className="flex flex-col gap-2" onSubmit={(event) => { event.preventDefault(); onSave(value.trim() || null) }}>
    <label className="flex flex-col gap-2 text-xs font-semibold">Ghi chú nội bộ<textarea className={PRODUCT_CONTROL + ' min-h-20 font-normal'} value={value} onChange={(event) => setValue(event.target.value)} disabled={busy} maxLength={4000} /></label>
    <ProductButton type="submit" secondary className="self-end" disabled={busy || value.trim() === (order.InternalNote ?? '').trim()}>Lưu ghi chú</ProductButton>
  </form>
}

export function SerialRow({ item }) {
  return <div className="flex flex-col gap-2 rounded-[10px] border border-admin-border p-3">
    <div className="flex items-center justify-between gap-3 text-xs"><strong>{item.Sku}</strong><span className="text-admin-muted">{item.SerialNumbers.length}/{item.Quantity} Serial/IMEI</span></div>
    <dl aria-label={'Serial/IMEI ' + item.Sku} className="m-0 flex flex-col gap-2 text-xs">
      {item.SerialNumbers.map(number => <div key={number} className="flex gap-2"><dt>Serial/IMEI:</dt><dd className="m-0 break-all">{number}</dd></div>)}
      {item.SerialNumbers.length < item.Quantity && <div className="flex gap-2"><dt>Serial/IMEI:</dt><dd className="m-0" /></div>}
    </dl>
  </div>
}
