import { useState } from 'react'
import { PROMOTION_STATUSES, PROMOTION_TYPES, promotionDateTime, promotionForm } from '../lib/promotions.js'
import { PromotionPopupButton } from './PromotionUi.jsx'
import PromotionTargetPicker from './PromotionTargetPicker.jsx'
import { ALL_PROMOTION_CATEGORIES, SAVED_PROMOTION_SCOPE, initialPromotionTargets, promotionTargetBody } from '../lib/promotion-targets.js'

const CONTROL = 'h-[42px] w-full min-w-0 rounded-[9px] border border-admin-border bg-white px-3 text-xs leading-[normal] font-normal text-admin-text placeholder:text-admin-muted disabled:bg-admin-page disabled:text-admin-muted'
function Field({ label, children }) { return <label className="flex min-w-0 flex-col gap-[7px] text-xs leading-[normal] font-medium">{label}{children}</label> }
function Select({ children, ...props }) {
  return <span className="relative block"><select className={CONTROL + ' appearance-none pr-8'} {...props}>{children}</select><span aria-hidden="true" className="pointer-events-none absolute top-0 right-3 flex h-full items-center text-xs text-admin-muted">▼</span></span>
}
function FormattedInput({ className = CONTROL, value, display, emptyDisplay, ...props }) {
  const [focused, setFocused] = useState(false)
  const overlay = !focused && (Boolean(value) || Boolean(emptyDisplay))
  return <span className="relative block"><input {...props} value={value} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} className={className + (overlay ? ' text-transparent! [&::-webkit-datetime-edit]:opacity-0' : '')} />{overlay && <span aria-hidden="true" className={'pointer-events-none absolute inset-y-0 left-3 flex max-w-[calc(100%-48px)] items-center truncate text-xs font-normal ' + (props.disabled || !value ? 'text-admin-muted' : 'text-admin-text')}>{value ? display : emptyDisplay}</span>}</span>
}
function MoneyInput(props) { return <FormattedInput {...props} display={Number(props.value).toLocaleString('vi-VN', { maximumFractionDigits: 2 })} /> }
function DateInput({ placeholder, ...props }) { return <FormattedInput type="datetime-local" step="1" {...props} emptyDisplay={placeholder} display={props.value ? promotionDateTime(props.value) : ''} /> }

export default function PromotionEditor({ row, products, categories, busy, error, onSave, onClose }) {
  const [form, setForm] = useState(() => promotionForm(row)), [validation, setValidation] = useState('')
  const [selection, setSelection] = useState(() => initialPromotionTargets(row, products))
  const locked = row?.Status === 'Active'
  const change = (key, value) => { setForm((previous) => ({ ...previous, [key]: value })); setValidation('') }
  const moneyProps = { type: 'number', min: '0', max: '9999999999999.99', step: '0.01', className: CONTROL + ' [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none', disabled: locked }
  function submit(event) {
    event.preventDefault()
    if (busy) return
    try {
      const targets = promotionTargetBody(selection, products, categories, row)
      setValidation(''); onSave({ ...form, ...targets })
    } catch (failure) { setValidation(failure.message) }
  }
  return <form onSubmit={submit} className="flex max-w-[630px] flex-col gap-[15px]">
    <fieldset disabled={busy} className="m-0 flex min-w-0 flex-col gap-[15px] border-0 p-0">
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Tên chương trình"><input aria-label="Tên chương trình" required maxLength={255} placeholder="Nhập tên chương trình" className={CONTROL} value={form.Name} onChange={(event) => change('Name', event.target.value)} /></Field>
        <Field label="Trạng thái"><Select aria-label="Trạng thái" value={form.Status} onChange={(event) => change('Status', event.target.value)}>{Object.entries(PROMOTION_STATUSES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
      </div>
      <Field label="Mô tả"><textarea aria-label="Mô tả" placeholder="Nhập mô tả chương trình khuyến mãi" className={CONTROL + ' h-[90px]! resize-y py-2.5'} value={form.Description} onChange={(event) => change('Description', event.target.value)} /></Field>
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Loại giảm giá"><Select aria-label="Loại giảm" disabled={locked} value={form.DiscountType} onChange={(event) => change('DiscountType', event.target.value)}>{Object.entries(PROMOTION_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
        <Field label="Giá trị giảm"><MoneyInput aria-label="Giá trị giảm" {...moneyProps} required max={form.DiscountType === 'Percentage' ? '100' : moneyProps.max} placeholder="Nhập giá trị giảm" value={form.DiscountValue} onChange={(event) => change('DiscountValue', event.target.value)} /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Đơn hàng tối thiểu"><MoneyInput aria-label="Đơn tối thiểu" {...moneyProps} required placeholder="Nhập giá trị đơn tối thiểu" value={form.MinOrderValue} onChange={(event) => change('MinOrderValue', event.target.value)} /></Field>
        <Field label="Danh mục"><Select aria-label="Danh mục áp dụng" required disabled={locked} value={selection.categoryId} onChange={(event) => { setSelection({ categoryId: event.target.value, allProducts: true, productIds: [], changed: true }); setValidation('') }}>
          <option value="" disabled hidden />
          <option value={ALL_PROMOTION_CATEGORIES}>Tất cả danh mục</option>
          {selection.categoryId === SAVED_PROMOTION_SCOPE && <option value={SAVED_PROMOTION_SCOPE} disabled>Phạm vi đã lưu (nhiều danh mục / sản phẩm)</option>}
          {categories.map((category) => <option key={category.CategoryId} value={category.CategoryId}>{category.Name}</option>)}
          {selection.categoryId && ![ALL_PROMOTION_CATEGORIES, SAVED_PROMOTION_SCOPE].includes(selection.categoryId) && !categories.some((category) => category.CategoryId === selection.categoryId) && <option value={selection.categoryId} disabled>Danh mục đã lưu</option>}
        </Select></Field>
      </div>
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Thời gian bắt đầu"><DateInput aria-label="Bắt đầu" placeholder="Chọn ngày giờ bắt đầu" required disabled={locked} value={form.StartDate} onChange={(event) => change('StartDate', event.target.value)} /></Field>
        <Field label="Thời gian kết thúc"><DateInput aria-label="Kết thúc" placeholder="Chọn ngày giờ kết thúc" required disabled={locked} value={form.EndDate} onChange={(event) => change('EndDate', event.target.value)} /></Field>
      </div>
      <PromotionTargetPicker key={selection.categoryId} products={products} selection={selection} disabled={busy || locked} onChange={(next) => { setSelection(next); setValidation('') }} />
      <details className="text-[11px] leading-[normal] text-admin-muted"><summary className="cursor-pointer">Thiết lập bổ sung</summary><div className="mt-3 max-w-[308px]"><Field label="Giảm tối đa (đồng)"><MoneyInput aria-label="Giảm tối đa" {...moneyProps} placeholder="Không giới hạn" value={form.MaxDiscountAmount} onChange={(event) => change('MaxDiscountAmount', event.target.value)} /></Field></div></details>
    </fieldset>
    <p className="m-0 text-[11px] leading-[normal] text-admin-muted">{locked ? 'Chương trình đang hoạt động: chỉ được sửa tên, mô tả và trạng thái.' : row ? 'Hệ thống kiểm tra các trường nhập liệu trước khi cập nhật và thông báo kết quả.' : 'Hệ thống kiểm tra định dạng và các trường bắt buộc trước khi thêm mới khuyến mãi.'}</p>
    {(error || validation) && <p role="alert" className="m-0 rounded-lg bg-red-50 p-3 text-xs text-admin-red">{validation || error}</p>}
    <div className="flex justify-end"><PromotionPopupButton secondary disabled={busy} onClick={onClose}>Hủy</PromotionPopupButton><PromotionPopupButton type="submit" disabled={busy}>{busy ? 'Đang lưu…' : row ? 'Cập nhật' : 'Thêm khuyến mãi mới'}</PromotionPopupButton></div>
  </form>
}
