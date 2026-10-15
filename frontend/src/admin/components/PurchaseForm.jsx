import { useRef, useState } from 'react'
import { formatDate, formatMoney } from '../../lib/format.js'
import { emptyPurchaseLine, purchaseCentsText, purchaseFormBody, purchaseFormDraft, purchaseFormTotal, purchaseLineCents } from '../lib/purchase-form.js'
import { variantLabel } from '../lib/purchases.js'
import { PurchaseButton } from './PurchaseUi.jsx'

const TITLE = 'm-0 text-[13px] leading-4 font-semibold'
const CONTROL = 'h-10 w-full min-w-0 rounded-lg border border-admin-border bg-white px-[11px] text-[10px] font-normal text-admin-text placeholder:text-admin-muted disabled:opacity-60'
const LINE_CONTROL = 'h-8 w-full min-w-0 rounded-md border border-admin-border bg-white px-2 text-[10px] text-admin-text placeholder:text-admin-muted disabled:opacity-60'

function Field({ label, children, className = '' }) {
  return <label className={'flex min-w-0 flex-col gap-[5px] text-[10px] leading-3 font-medium ' + className}>{label}{children}</label>
}

export default function PurchaseForm({ po, role, suppliers, variants, busy, onSave, onCancel, onError, error, progress, blocked = false }) {
  const [form, setForm] = useState(() => purchaseFormDraft(po))
  const nextKey = useRef(2)
  const edit = Boolean(po)
  const rows = form.Items
  const receivedByVariant = new Map((po?.Items ?? []).map((item) => [item.ProductVariantId, item.ReceivedQuantity]))
  const existingIds = new Set(po?.Items.map((item) => item.ProductVariantId) ?? [])
  const unavailable = blocked || suppliers.loading || variants.loading || Boolean(suppliers.error || variants.error)
  const supplierRows = (suppliers.data ?? []).filter((supplier) => supplier.IsActive || supplier.SupplierId === po?.SupplierId)
  const catalog = (variants.data ?? []).filter((variant) => !variant.IsDeleted || existingIds.has(variant.ProductVariantId))
  function changeLine(key, patch) { setForm((previous) => ({ ...previous, Items: previous.Items.map((item) => item.key === key ? { ...item, ...patch } : item) })); onError('') }
  async function save(event) {
    event.preventDefault()
    if (busy || unavailable) return
    let body
    try {
      body = purchaseFormBody(form)
      if (form.SupplierId !== po?.SupplierId && !supplierRows.some((supplier) => supplier.SupplierId === form.SupplierId && supplier.IsActive)) throw new Error('Vui lòng chọn nhà cung cấp đang hoạt động.')
      for (const item of body.Items) if (!catalog.some((variant) => variant.ProductVariantId === item.ProductVariantId && (!variant.IsDeleted || existingIds.has(item.ProductVariantId)))) throw new Error('Sản phẩm đã chọn không còn khả dụng. Vui lòng chọn lại.')
    } catch (failure) { onError(failure.message); return }
    await onSave(body)
  }
  return <form aria-label={edit ? 'Sửa phiếu nhập' : 'Tạo phiếu nhập'} onSubmit={save} className="flex min-w-0 flex-col gap-3.5">
    {error && <p role="alert" className="m-0 rounded-[9px] bg-red-50 p-3 text-xs text-red-700">{error}</p>}
    {progress && <p role="status" className="m-0 text-xs text-admin-muted">{progress}</p>}
    <fieldset disabled={busy} className="m-0 flex min-w-0 flex-col gap-3.5 border-0 p-0">
      <section aria-label="Thông tin chung" className="flex min-w-0 flex-col gap-2.5 rounded-xl border border-admin-border bg-white p-4"><h3 className={TITLE}>Thông tin chung</h3>
        <div className="flex min-w-0 items-start gap-3">
          <Field label="Nhà cung cấp" className="w-[330px]"><select aria-label="Nhà cung cấp" required className={CONTROL} value={form.SupplierId} disabled={suppliers.loading || Boolean(suppliers.error)} onChange={(event) => { setForm({ ...form, SupplierId: event.target.value }); onError('') }}><option value="" disabled hidden />{supplierRows.map((supplier) => <option key={supplier.SupplierId} value={supplier.SupplierId} disabled={!supplier.IsActive}>{supplier.Name}{!supplier.IsActive ? ' (Ẩn)' : ''}</option>)}</select></Field>
          <Field label="Mã phiếu" className="w-[250px]"><input aria-label="Mã phiếu" readOnly className={CONTROL + ' text-admin-muted'} value={po?.PurchaseOrderCode ?? 'Tự động tạo sau khi lưu'} /></Field>
          <Field label="Ngày lập" className="w-[200px]"><input aria-label="Ngày lập" readOnly className={CONTROL + ' text-admin-muted'} value={formatDate(form.CreatedDate)} title="Ngày lập do hệ thống tự ghi" /></Field>
        </div>
        <Field label="Ghi chú" className="w-[812px] max-w-full"><input aria-label="Ghi chú phiếu" className={CONTROL} placeholder="Nhập ghi chú cho phiếu nhập" maxLength={4000} value={form.Note} onChange={(event) => { setForm({ ...form, Note: event.target.value }); onError('') }} /></Field>
      </section>
      <section aria-label="Sản phẩm nhập" className="flex min-w-0 flex-col gap-2.5 rounded-xl border border-admin-border bg-white p-3.5">
        <div className="flex items-center justify-between"><h3 className={TITLE}>Sản phẩm nhập</h3><PurchaseButton secondary disabled={unavailable} onClick={() => setForm((previous) => ({ ...previous, Items: [...previous.Items, emptyPurchaseLine('new-' + nextKey.current++)] }))}>+ Thêm sản phẩm</PurchaseButton></div>
        <div className="w-full overflow-x-auto" tabIndex={0}><table aria-label="Danh sách sản phẩm nhập" className="w-full table-fixed border-collapse text-left text-[10px] leading-3"><colgroup><col className="w-[36%]" /><col className="w-[10%]" /><col className="w-[10%]" /><col className="w-[16%]" /><col className="w-[18%]" /><col className="w-[10%]" /></colgroup>
          <thead><tr>{['Sản phẩm / biến thể', 'SL đặt', 'SL thực nhận', 'Đơn giá nhập', 'Thành tiền', 'Thao tác'].map((label) => <th scope="col" key={label} className="h-12 pr-1.5 pl-2 text-[9px] font-semibold text-admin-muted">{label}</th>)}</tr></thead>
          <tbody>{rows.map((line, index) => <tr key={line.key} className="border-b border-admin-border"><td className="h-12 py-1 pr-1.5 pl-2"><select aria-label={'Sản phẩm / biến thể dòng ' + (index + 1)} className={LINE_CONTROL} value={line.ProductVariantId} disabled={variants.loading || Boolean(variants.error)} onChange={(event) => changeLine(line.key, { ProductVariantId: event.target.value })}><option value="" disabled hidden />{catalog.map((variant) => <option key={variant.ProductVariantId} value={variant.ProductVariantId} disabled={rows.some((row) => row.key !== line.key && row.ProductVariantId === variant.ProductVariantId) || (variant.IsDeleted && variant.ProductVariantId !== line.ProductVariantId)}>{variantLabel(variant)}{variant.IsDeleted ? ' (Ẩn)' : ''}</option>)}</select></td>
            <td className="h-12 py-1 pr-1.5 pl-2"><input aria-label={'Số lượng đặt dòng ' + (index + 1)} type="number" min="1" max="2147483647" step="1" className={LINE_CONTROL} placeholder="0" value={line.OrderedQuantity} onChange={(event) => changeLine(line.key, { OrderedQuantity: event.target.value })} /></td>
            <td className="h-12 py-1 pr-1.5 pl-2"><input aria-label={'Số lượng thực nhận dòng ' + (index + 1)} aria-describedby="purchase-received-hint" type="number" readOnly className={LINE_CONTROL + ' bg-admin-page text-admin-muted'} value={receivedByVariant.get(line.ProductVariantId) ?? 0} /></td>
            <td className="h-12 py-1 pr-1.5 pl-2"><input aria-label={'Đơn giá nhập dòng ' + (index + 1)} type="number" min="0" step="0.01" className={LINE_CONTROL} placeholder="0" value={line.UnitPrice} onChange={(event) => changeLine(line.key, { UnitPrice: event.target.value })} /></td>
            <td className="h-12 py-1 pr-1.5 pl-2"><output aria-label={'Thành tiền dòng ' + (index + 1)}>{formatMoney(purchaseCentsText(purchaseLineCents(line)))}</output></td>
            <td className="h-12 py-1 pr-1.5 pl-2"><button type="button" aria-label={'Xóa dòng ' + (index + 1)} disabled={rows.length <= 1} title={rows.length <= 1 ? 'Phiếu cần ít nhất một dòng sản phẩm' : 'Xóa dòng sản phẩm'} className="cursor-pointer rounded p-1 text-[10px] text-admin-red hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40" onClick={() => { setForm((previous) => ({ ...previous, Items: previous.Items.filter((item) => item.key !== line.key) })); onError('') }}>Xóa</button></td>
          </tr>)}</tbody>
        </table></div>
        <p id="purchase-received-hint" className="m-0 text-[10px] leading-normal text-admin-muted">Thực nhận được cập nhật khi nhận hàng vào kho. Phiếu mới có thực nhận bằng 0.</p>
      </section>
      <div className="flex items-center gap-1"><p className="mr-auto mb-0 text-[10px] leading-3 text-admin-muted">{edit ? 'Chỉ có thể sửa phiếu khi chưa được quản trị viên xác nhận.' : role === 'Admin' ? 'Phiếu do quản trị viên lập được xác nhận ngay.' : 'Phiếu mới được tạo ở trạng thái “Chờ xác nhận”.'}</p><span className="text-[11px] leading-[13px] font-medium text-admin-muted">Tổng tiền:</span><output aria-label="Tổng tiền phiếu nhập" className="text-[15px] leading-[18px] font-bold">{formatMoney(purchaseCentsText(purchaseFormTotal(rows)))}</output></div>
      <div className="flex justify-end gap-0"><PurchaseButton secondary onClick={onCancel}>Hủy</PurchaseButton><PurchaseButton type="submit" disabled={unavailable} loading={busy}>{edit ? 'Cập nhật phiếu' : 'Lưu phiếu'}</PurchaseButton></div>
    </fieldset>
  </form>
}
