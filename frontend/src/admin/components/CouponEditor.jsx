import { useState } from 'react'
import { couponBody, couponError, couponForm, couponStatus } from '../lib/coupons.js'
import { PROMOTION_TYPES, promotionDateTime, promotionMoney, promotionValue } from '../lib/promotions.js'
import { CouponStatus } from './CouponUi.jsx'
import CouponProgram from './CouponProgram.jsx'
import { PromotionPopupButton } from './PromotionUi.jsx'
import { useCouponClock } from '../hooks/useCouponRefresh.js'

const CONTROL = 'h-[42px] w-full min-w-0 rounded-[9px] border border-admin-border bg-white px-3 text-xs leading-[normal] text-admin-text disabled:bg-admin-page disabled:text-admin-muted'
const monotonicNow = () => performance.now()
function Field({ label, children }) { return <label className="flex min-w-0 flex-col gap-[7px] text-xs leading-[normal] font-medium">{label}{children}</label> }
function Inherited({ label, value = '' }) { return <Field label={label}><input aria-label={label} readOnly className={CONTROL + ' bg-admin-page! text-admin-muted!'} value={value} /></Field> }
function Select({ children, ...props }) { return <span className="relative block"><select className={CONTROL + ' appearance-none pr-8'} {...props}>{children}</select><span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[11px] text-admin-muted">▼</span></span> }

export default function CouponEditor({ row, promotions, promotionId, now, busy, failure, onSave, onClose }) {
  const [form, setForm] = useState(() => couponForm(row, promotions.some((item) => item.PromotionId === promotionId) ? promotionId : ''))
  const [validation, setValidation] = useState('')
  const elapsed = useCouponClock(monotonicNow)
  const [openedAt] = useState(monotonicNow)
  const program = promotions.find((item) => item.PromotionId === form.PromotionId)
  const serverTime = Date.parse(program?.EvaluatedAt ?? row?.EvaluatedAt ?? '')
  const previewNow = Number.isFinite(serverTime) ? serverTime + Math.max(0, elapsed - openedAt) : now
  let valid = Boolean(program)
  try { couponBody(form, row?.UsedCount ?? 0) } catch { valid = false }
  function change(key, value) { setForm((previous) => ({ ...previous, [key]: value })); setValidation('') }
  function submit(event) {
    event.preventDefault()
    if (busy) return
    try {
      couponBody(form, row?.UsedCount ?? 0)
      if (!program) throw new Error('Vui lòng chọn chương trình khuyến mãi.')
      setValidation(''); onSave(form)
    } catch (error) { setValidation(error.message) }
  }
  return <form onSubmit={submit} className="flex max-w-[630px] min-w-0 flex-col gap-[15px]">
    <fieldset disabled={busy} className="m-0 flex min-w-0 flex-col gap-[15px] border-0 p-0">
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Tên mã giảm giá"><input autoFocus className={CONTROL} aria-label="Tên mã giảm giá" value={form.Name} onChange={(event) => change('Name', event.target.value)} required maxLength={255} placeholder="Nhập tên mã giảm giá" /></Field>
        <Field label="Mã giảm giá"><input className={CONTROL} aria-label="Mã giảm giá" value={form.Code} onChange={(event) => change('Code', event.target.value)} required maxLength={50} autoComplete="off" spellCheck={false} placeholder="Nhập mã khách hàng sử dụng" /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Chương trình khuyến mãi"><Select aria-label="Chương trình khuyến mãi" value={form.PromotionId} onChange={(event) => change('PromotionId', event.target.value)} required>{promotions.length > 0 && <option value="" disabled hidden />}{promotions.map((item) => <option key={item.PromotionId} value={item.PromotionId}>{item.Name}</option>)}</Select></Field>
        <Inherited label="Trạng thái" value="Hệ thống tự cập nhật" />
      </div>
      <Field label="Mô tả chương trình"><textarea aria-label="Mô tả chương trình" readOnly className={CONTROL + ' h-[90px]! resize-none bg-admin-page! py-2.5 text-admin-muted!'} value={program?.Description ?? ''} /></Field>
      <div className="grid grid-cols-2 gap-3.5"><Inherited label="Loại giảm giá" value={program ? PROMOTION_TYPES[program.DiscountType] : ''} /><Inherited label="Giá trị giảm" value={program ? promotionValue(program) : ''} /></div>
      <div className="grid grid-cols-2 gap-3.5">
        <Inherited label="Đơn hàng tối thiểu" value={program ? promotionMoney(program.MinOrderValue) : ''} />
        <Field label="Giới hạn lượt dùng"><input className={CONTROL} aria-label="Giới hạn lượt dùng" type="number" min={row?.UsedCount ?? 0} max="2147483647" step="1" placeholder="Không giới hạn" value={form.UsageLimit} onChange={(event) => change('UsageLimit', event.target.value)} /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3.5"><Inherited label="Thời gian bắt đầu" value={program ? promotionDateTime(program.StartDate) : ''} /><Inherited label="Thời gian kết thúc" value={program ? promotionDateTime(program.EndDate) : ''} /></div>
      <div className="grid grid-cols-2 gap-3.5"><Inherited label="Giảm tối đa" value={program ? program.MaxDiscountAmount == null ? 'Không giới hạn' : promotionMoney(program.MaxDiscountAmount) : ''} /><Inherited label="Lượt đã sử dụng" value={row?.UsedCount ?? 0} /></div>
    </fieldset>
    <div className="flex items-center justify-between gap-3 text-xs"><span className="font-medium text-admin-muted">Trạng thái hiện tại</span>{program && <CouponStatus value={couponStatus({ ...form, UsageLimit: form.UsageLimit.trim() === '' ? null : Number(form.UsageLimit), UsedCount: row?.UsedCount ?? 0 }, program, previewNow)} />}</div>
    <p className="m-0 text-[11px] leading-relaxed text-admin-muted">Các ô nền xám lấy từ chương trình mẹ và không thể chỉnh sửa tại đây. Để trống giới hạn lượt dùng nếu không giới hạn; nhập 0 nghĩa là hết lượt.</p>
    <CouponProgram promotion={program} busy={busy} />
    {(validation || failure) && <p role="alert" className="m-0 rounded-lg bg-red-50 p-3 text-xs text-admin-red">{validation || couponError(failure)}</p>}
    <div className="flex justify-end"><PromotionPopupButton secondary disabled={busy} onClick={onClose}>Hủy</PromotionPopupButton><PromotionPopupButton type="submit" disabled={busy || !valid}>{busy ? 'Đang lưu…' : row ? 'Cập nhật mã' : 'Thêm mã giảm giá'}</PromotionPopupButton></div>
  </form>
}
