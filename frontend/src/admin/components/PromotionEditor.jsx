import { useState } from 'react'
import { PROMOTION_MODES, PROMOTION_STATUSES, PROMOTION_TYPES, promotionBody, promotionDateTime, promotionForm, promotionMoney } from '../lib/promotions.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { request } from '../../services/api/client.js'
import { PromotionPopupButton } from './PromotionUi.jsx'
import PromotionTargetPicker from './PromotionTargetPicker.jsx'
import { ALL_PROMOTION_CATEGORIES, SAVED_PROMOTION_SCOPE, initialPromotionTargets, promotionCategoryOptions, promotionTargetBody } from '../lib/promotion-targets.js'

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
  const auth = useInternalAuth()
  const [preview, setPreview] = useState(null), [previewBusy, setPreviewBusy] = useState(false)
  const [form, setForm] = useState(() => promotionForm(row)), [validation, setValidation] = useState('')
  const [selection, setSelection] = useState(() => initialPromotionTargets(row, products, categories))
  const locked = row?.Status === 'Active'
  const change = (key, value) => { setForm((previous) => ({ ...previous, [key]: value })); setValidation(''); setPreview(null) }
  const moneyProps = { type: 'number', min: '0', max: '9999999999999.99', step: '0.01', className: CONTROL + ' [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none', disabled: locked }
  function submit(event) {
    event.preventDefault()
    if (busy) return
    try {
      const targets = promotionTargetBody(selection, products, categories, row)
      setValidation(''); onSave({ ...form, ...targets })
    } catch (failure) { setValidation(failure.message) }
  }
  async function previewPrices() {
    if (busy || previewBusy) return
    setValidation(''); setPreview(null)
    try {
      const body = promotionBody({ ...form, ...promotionTargetBody(selection, products, categories, row) })
      setPreviewBusy(true)
      setPreview(await auth.withAccessToken((accessToken) => request('/admin/promotions/pricing-preview', { method: 'POST', accessToken, body })))
    } catch (failure) { setValidation(failure.message) }
    finally { setPreviewBusy(false) }
  }
  return <form onSubmit={submit} className="flex max-w-[630px] flex-col gap-[15px]">
    <fieldset disabled={busy || previewBusy} className="m-0 flex min-w-0 flex-col gap-[15px] border-0 p-0">
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Tên chương trình"><input aria-label="Tên chương trình" required maxLength={255} placeholder="Nhập tên chương trình" className={CONTROL} value={form.Name} onChange={(event) => change('Name', event.target.value)} /></Field>
        <Field label="Trạng thái"><Select aria-label="Trạng thái" value={form.Status} onChange={(event) => change('Status', event.target.value)}>{Object.entries(PROMOTION_STATUSES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
      </div>
      <Field label="Mô tả"><textarea aria-label="Mô tả" placeholder="Nhập mô tả chương trình khuyến mãi" className={CONTROL + ' h-[90px]! resize-y py-2.5'} value={form.Description} onChange={(event) => change('Description', event.target.value)} /></Field>
      <Field label="Cách áp dụng"><Select aria-label="Cách áp dụng" disabled={locked} value={form.ApplyMode} onChange={(event) => { change('ApplyMode', event.target.value); if (event.target.value === 'Automatic') change('MinOrderValue', '0') }}>{Object.entries(PROMOTION_MODES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
      {form.ApplyMode === 'Automatic' && <p className="m-0 rounded-lg bg-blue-50 p-3 text-xs leading-relaxed text-admin-text">Giảm tự động cho mọi khách, tính trên từng sản phẩm. Giá sau giảm phải từ giá vốn trở lên; phiên bản chưa có giá vốn sẽ không được giảm. Khi nhiều chương trình cùng áp dụng, chọn giá hợp lệ thấp nhất.</p>}
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Loại giảm giá"><Select aria-label="Loại giảm" disabled={locked} value={form.DiscountType} onChange={(event) => change('DiscountType', event.target.value)}>{Object.entries(PROMOTION_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
        <Field label="Giá trị giảm"><MoneyInput aria-label="Giá trị giảm" {...moneyProps} required max={form.DiscountType === 'Percentage' ? '100' : moneyProps.max} placeholder="Nhập giá trị giảm" value={form.DiscountValue} onChange={(event) => change('DiscountValue', event.target.value)} /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Đơn hàng tối thiểu"><MoneyInput aria-label="Đơn tối thiểu" {...moneyProps} disabled={locked || form.ApplyMode === 'Automatic'} required placeholder="Nhập giá trị đơn tối thiểu" value={form.MinOrderValue} onChange={(event) => change('MinOrderValue', event.target.value)} /></Field>
        <Field label={form.ApplyMode === 'Automatic' ? 'Giảm tối đa mỗi sản phẩm (đồng)' : 'Giảm tối đa (đồng)'}><MoneyInput aria-label="Giảm tối đa" {...moneyProps} placeholder="Không giới hạn" value={form.MaxDiscountAmount} onChange={(event) => change('MaxDiscountAmount', event.target.value)} /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Thời gian bắt đầu"><DateInput aria-label="Bắt đầu" placeholder="Chọn ngày giờ bắt đầu" required disabled={locked} value={form.StartDate} onChange={(event) => change('StartDate', event.target.value)} /></Field>
        <Field label="Thời gian kết thúc"><DateInput aria-label="Kết thúc" placeholder="Chọn ngày giờ kết thúc" required disabled={locked} value={form.EndDate} onChange={(event) => change('EndDate', event.target.value)} /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="Danh mục"><Select aria-label="Danh mục áp dụng" required disabled={locked} value={selection.categoryId} onChange={(event) => { setSelection({ categoryId: event.target.value, allProducts: true, productIds: [], changed: true }); setValidation(''); setPreview(null) }}>
          <option value="" disabled hidden>Chọn danh mục áp dụng</option>
          <option value={ALL_PROMOTION_CATEGORIES}>Tất cả danh mục</option>
          {selection.categoryId === SAVED_PROMOTION_SCOPE && <option value={SAVED_PROMOTION_SCOPE} disabled>Phạm vi đã lưu (nhiều danh mục / sản phẩm)</option>}
          {promotionCategoryOptions(categories).map(({ category, depth }) => <option key={category.CategoryId} value={category.CategoryId}>{'   '.repeat(depth) + category.Name}</option>)}
          {selection.categoryId && ![ALL_PROMOTION_CATEGORIES, SAVED_PROMOTION_SCOPE].includes(selection.categoryId) && !categories.some((category) => category.CategoryId === selection.categoryId) && <option value={selection.categoryId} disabled>Danh mục đã lưu</option>}
        </Select></Field>
        <PromotionTargetPicker key={selection.categoryId} products={products} categories={categories} selection={selection} disabled={busy || previewBusy || locked} onChange={(next) => { setSelection(next); setValidation(''); setPreview(null) }} />
      </div>
    </fieldset>
    {form.ApplyMode === 'Automatic' && <div className="flex flex-col gap-2">
      <PromotionPopupButton secondary disabled={busy || previewBusy} onClick={() => void previewPrices()}>{previewBusy ? 'Đang tính giá và lãi…' : 'Xem giá và lãi dự kiến'}</PromotionPopupButton>
      {preview && <div className="max-h-64 overflow-auto rounded-lg border border-admin-border">
        <p className="m-0 p-2 text-xs">{preview.Total} phiên bản · Lãi gộp mỗi chiếc, chưa tính coupon.</p>
        <table className="w-full text-left text-[11px]"><thead><tr><th className="p-2">SKU</th><th className="p-2">Giá vốn</th><th className="p-2">Sau giảm</th><th className="p-2">Lãi gộp</th></tr></thead>
          <tbody>{preview.Items.map((item) => <tr key={item.ProductVariantId} title={item.ProductName} className={item.IsValid ? '' : 'bg-red-50 text-admin-red'}>
            <td className="p-2">{item.Sku}{item.Reason && <span className="block">{item.Reason}</span>}</td><td className="p-2">{promotionMoney(item.CostPrice)}</td><td className="p-2">{promotionMoney(item.SalePrice)}</td><td className="p-2">{item.EstimatedGrossProfit === null ? 'Chưa có giá vốn' : promotionMoney(item.EstimatedGrossProfit)}</td>
          </tr>)}</tbody></table>
      </div>}
    </div>}
    <p className="m-0 text-[11px] leading-[normal] text-admin-muted">{locked ? 'Chương trình đang hoạt động: chỉ được sửa tên, mô tả và trạng thái.' : row ? 'Hệ thống kiểm tra các trường nhập liệu trước khi cập nhật và thông báo kết quả.' : 'Hệ thống kiểm tra định dạng và các trường bắt buộc trước khi thêm mới khuyến mãi.'}</p>
    {(error || validation) && <p role="alert" className="m-0 rounded-lg bg-red-50 p-3 text-xs text-admin-red">{validation || error}</p>}
    <div className="flex justify-end gap-2"><PromotionPopupButton secondary disabled={busy || previewBusy} onClick={onClose}>Hủy</PromotionPopupButton><PromotionPopupButton type="submit" disabled={busy || previewBusy}>{busy ? 'Đang lưu…' : row ? 'Cập nhật' : 'Thêm khuyến mãi mới'}</PromotionPopupButton></div>
  </form>
}
