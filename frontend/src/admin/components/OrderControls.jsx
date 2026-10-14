import { useState } from 'react'
import { PRODUCT_CONTROL, ProductButton } from './ProductUi.jsx'

export function InternalNote({ order, busy, onSave }) {
  const [value, setValue] = useState(order.InternalNote ?? '')
  return <form className="flex flex-col gap-2" onSubmit={(event) => { event.preventDefault(); onSave(value.trim() || null) }}>
    <label className="flex flex-col gap-2 text-xs font-semibold">Ghi chú nội bộ<textarea className={PRODUCT_CONTROL + ' min-h-20 font-normal'} value={value} onChange={(event) => setValue(event.target.value)} disabled={busy} maxLength={4000} /></label>
    <ProductButton type="submit" secondary className="self-end" disabled={busy || value.trim() === (order.InternalNote ?? '').trim()}>Lưu ghi chú</ProductButton>
  </form>
}

export function SerialRow({ item, busy, editable, onAssign, onRelease }) {
  const [value, setValue] = useState('')
  return <div className="flex flex-col gap-2 rounded-[10px] border border-admin-border p-3">
    <div className="flex items-center justify-between gap-3 text-xs"><strong>{item.Sku}</strong><span className="text-admin-muted">{item.SerialNumbers.length}/{item.Quantity} Serial/IMEI</span></div>
    <div className="flex flex-wrap gap-2">{item.SerialNumbers.map((number) => <span key={number} className="inline-flex items-center gap-2 rounded-md bg-admin-soft px-2 py-1 text-xs text-admin-navy">{number}
      {editable && <button type="button" className="cursor-pointer border-0 bg-transparent text-admin-red disabled:opacity-50" disabled={busy} aria-label={'Gỡ Serial/IMEI ' + number} onClick={() => onRelease(number)}>×</button>}
    </span>)}{!item.SerialNumbers.length && <span className="text-xs text-admin-muted">Chưa gán Serial/IMEI.</span>}</div>
    {editable && item.SerialNumbers.length < item.Quantity && <form className="flex items-end gap-2" onSubmit={async (event) => { event.preventDefault(); if (await onAssign(item, value)) setValue('') }}>
      <label className="flex flex-1 flex-col gap-1 text-xs">Serial/IMEI cho {item.Sku}<textarea className={PRODUCT_CONTROL + ' min-h-16 text-xs!'} placeholder="Quét hoặc nhập mã; mỗi mã một dòng" value={value} onChange={(event) => setValue(event.target.value)} disabled={busy} maxLength={16000} /></label>
      <ProductButton type="submit" secondary disabled={busy || !value.trim()}>Gán mã</ProductButton>
    </form>}
  </div>
}
