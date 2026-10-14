import { useState } from 'react'
import { reviewImageUrl } from '../lib/reviews.js'
import { ProductButton } from './ProductUi.jsx'

export function ReviewButton({ secondary = false, className = '', ...props }) {
  return <ProductButton secondary={secondary} className={'h-[31px]! rounded-[9px]! px-[13px]! text-[10px]! ' + (secondary ? 'text-admin-text! ' : '') + className} {...props} />
}
export function ReviewRating({ value, className = '' }) {
  if (!Number.isInteger(value) || value < 1 || value > 5) return <span>—</span>
  return <span role="img" aria-label={value + ' trên 5 sao'} className={'text-[9px] leading-[normal] whitespace-nowrap text-[#ffc629] ' + className}>{'★'.repeat(value)}{'☆'.repeat(5 - value)}</span>
}
export function ReviewImage({ entry, number }) {
  const [failed, setFailed] = useState(false)
  const url = reviewImageUrl(entry.ImageUrl)
  return url && !failed ? <a href={url} target="_blank" rel="noopener noreferrer" className="block shrink-0 rounded-lg"><img src={url} alt={'Ảnh đánh giá ' + number} className="size-[120px] rounded-lg border border-admin-border object-cover" loading="lazy" onError={() => setFailed(true)} /></a> : <span className="grid size-[120px] place-items-center rounded-lg bg-admin-page p-2 text-center text-xs text-admin-muted">Ảnh không khả dụng</span>
}
