import { useEffect, useId, useRef, useState } from 'react'
import { ALL_PROMOTION_CATEGORIES, SAVED_PROMOTION_SCOPE, promotionCategoryFamily, promotionCategoryOptions, promotionSelectedFamily } from '../lib/promotion-targets.js'

const searchKey = (text) => String(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLocaleLowerCase('vi')

export default function PromotionCategoryPicker({ categories, selection, onChange, disabled }) {
  const [open, setOpen] = useState(false), [keyword, setKeyword] = useState('')
  const root = useRef(null), trigger = useRef(null), panelId = useId(), hintId = useId()
  const all = selection.categoryIds.includes(ALL_PROMOTION_CATEGORIES)
  const saved = selection.categoryIds.includes(SAVED_PROMOTION_SCOPE)
  const family = promotionSelectedFamily(selection.categoryIds, categories)
  const summary = all ? 'Tất cả danh mục' : saved ? 'Theo phạm vi đã lưu' : selection.categoryIds.map((id) => categories.find((category) => category.CategoryId === id)?.Name ?? 'Danh mục đã lưu').join(', ') || 'Chọn danh mục áp dụng'
  const shown = promotionCategoryOptions(categories).filter(({ category }) => searchKey(category.Name).includes(searchKey(keyword.trim())))
  useEffect(() => {
    if (!open) return
    const outside = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  function choose(categoryIds) {
    onChange({ categoryIds, allProducts: true, productIds: [], changed: true })
  }
  function toggle(categoryId, checked) {
    const current = all || saved ? [] : selection.categoryIds
    const descendants = promotionCategoryFamily(categoryId, categories)
    choose(checked ? [...current.filter((id) => !descendants.includes(id)), categoryId] : current.filter((id) => id !== categoryId))
  }
  return <div ref={root} className="relative flex min-w-0 flex-col gap-[7px]" onKeyDown={(event) => { if (open && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus() } }}>
    <span className="text-xs leading-[normal] font-medium">Danh mục</span>
    <div className="relative">
    <button ref={trigger} type="button" aria-label="Danh mục áp dụng" aria-describedby={hintId} aria-expanded={open && !disabled} aria-controls={open && !disabled ? panelId : undefined} disabled={disabled} title={summary} onClick={() => setOpen((value) => !value)} className="relative h-[42px] w-full min-w-0 cursor-pointer truncate rounded-[9px] border border-admin-border bg-white py-0 pr-8 pl-3 text-left text-xs leading-[normal] text-admin-text disabled:cursor-default disabled:bg-admin-page disabled:text-admin-muted">
      {summary}<span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-admin-muted">▼</span>
    </button>
    {open && !disabled && <div id={panelId} role="group" aria-label="Chọn danh mục khuyến mãi" className="absolute right-0 bottom-[calc(100%+6px)] left-0 z-20 flex flex-col gap-3 rounded-[9px] border border-admin-border bg-white p-3 shadow-lg">
      <input type="search" aria-label="Tìm danh mục áp dụng" placeholder="Tìm danh mục..." value={keyword} onChange={(event) => setKeyword(event.target.value)} className="h-[34px] w-full rounded-lg border border-admin-border bg-white px-3 text-xs text-admin-text" />
      <label className="flex cursor-pointer items-start gap-2 text-xs font-medium"><input type="checkbox" className="mt-0.5" checked={all} onChange={(event) => choose(event.target.checked ? [ALL_PROMOTION_CATEGORIES] : [])} />Tất cả danh mục</label>
      <div className="flex max-h-[200px] flex-col gap-2 overflow-y-auto text-xs">
        {!shown.length && <p className="m-0 text-admin-muted">Không có danh mục phù hợp.</p>}
        {shown.map(({ category, depth }) => {
          const inherited = !all && !selection.categoryIds.includes(category.CategoryId) && family.includes(category.CategoryId)
          return <label key={category.CategoryId} style={{ paddingLeft: depth * 12 }} className={'flex items-start gap-2 ' + (inherited ? 'text-admin-muted' : 'cursor-pointer')} title={inherited ? 'Đã bao gồm trong danh mục cha đang chọn' : undefined}>
            <input type="checkbox" className="mt-0.5" checked={family.includes(category.CategoryId)} disabled={inherited} onChange={(event) => toggle(category.CategoryId, event.target.checked)} />{category.Name}
          </label>
        })}
      </div>
    </div>}
    </div>
    <p id={hintId} className="m-0 text-[11px] leading-relaxed text-admin-muted">Có thể chọn nhiều danh mục. Chọn danh mục cha sẽ áp dụng cho cả danh mục con.</p>
  </div>
}
