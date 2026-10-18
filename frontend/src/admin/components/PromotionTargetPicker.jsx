import { useEffect, useId, useRef, useState } from 'react'
import { promotionTargetName } from '../lib/promotions.js'
import { ALL_PROMOTION_CATEGORIES, SAVED_PROMOTION_SCOPE, promotionProductCategory } from '../lib/promotion-targets.js'

const searchKey = (text) => String(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLocaleLowerCase('vi')
export default function PromotionTargetPicker({ products, selection, onChange, disabled }) {
  const [open, setOpen] = useState(false), [keyword, setKeyword] = useState('')
  const root = useRef(null), trigger = useRef(null), panelId = useId()
  const unavailable = disabled || !selection.categoryId || [ALL_PROMOTION_CATEGORIES, SAVED_PROMOTION_SCOPE].includes(selection.categoryId)
  useEffect(() => {
    if (!open) return
    const outside = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  const available = products.filter((product) => promotionProductCategory(product) === selection.categoryId)
  const shown = available.filter((product) => searchKey(product.Name).includes(searchKey(keyword.trim())))
  const summary = !selection.categoryId ? 'Chọn danh mục trước' : selection.categoryId === SAVED_PROMOTION_SCOPE ? 'Theo phạm vi đã lưu' : selection.allProducts ? 'Tất cả sản phẩm' : promotionTargetName(selection.productIds, available, 'ProductId') || 'Chọn sản phẩm áp dụng'
  return <div ref={root} className="relative flex min-w-0 flex-col gap-[7px]" onKeyDown={(event) => { if (open && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus() } }}>
    <span className="text-xs leading-[normal] font-medium">Sản phẩm</span>
    <button ref={trigger} type="button" aria-label="Sản phẩm áp dụng" aria-expanded={open && !unavailable} aria-controls={open && !unavailable ? panelId : undefined} disabled={unavailable} onClick={() => setOpen((value) => !value)} className="relative h-[42px] w-full min-w-0 cursor-pointer truncate rounded-[9px] border border-admin-border bg-white py-0 pr-8 pl-3 text-left text-xs leading-[normal] text-admin-text disabled:cursor-default disabled:bg-admin-page disabled:text-admin-muted">
      {summary}<span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-admin-muted">▼</span>
    </button>
    {open && !unavailable && <div id={panelId} className="absolute top-[calc(100%+6px)] right-0 left-0 z-20 flex flex-col gap-3 rounded-[9px] border border-admin-border bg-white p-3 shadow-lg">
      <input type="search" aria-label="Tìm sản phẩm áp dụng" placeholder="Tìm theo tên..." value={keyword} onChange={(event) => setKeyword(event.target.value)} className="h-[34px] w-full rounded-lg border border-admin-border bg-white px-3 text-xs text-admin-text" />
      <label className="flex cursor-pointer items-start gap-2 text-xs font-medium"><input type="checkbox" className="mt-0.5" checked={selection.allProducts} onChange={(event) => onChange({ ...selection, allProducts: event.target.checked, productIds: [], changed: true })} />Tất cả sản phẩm</label>
      <div className="flex max-h-[160px] flex-col gap-2 overflow-y-auto text-xs">
        {!shown.length && <p className="m-0 text-admin-muted">Không có sản phẩm phù hợp trong danh mục này.</p>}
        {shown.map((product) => <label key={product.ProductId} className="flex cursor-pointer items-start gap-2"><input type="checkbox" className="mt-0.5" checked={!selection.allProducts && selection.productIds.includes(product.ProductId)} onChange={(event) => onChange({ ...selection, allProducts: false, productIds: event.target.checked ? [...(selection.allProducts ? [] : selection.productIds), product.ProductId] : selection.productIds.filter((id) => id !== product.ProductId), changed: true })} />{product.Name}</label>)}
      </div>
    </div>}
  </div>
}
