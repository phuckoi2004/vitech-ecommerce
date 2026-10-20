import { useState } from 'react'
import Button from '../../components/shared/Button.jsx'
import { productInitials } from '../../lib/admin-products.js'

export function ProductButton({ secondary = false, className = '', ...props }) {
  return <Button variant={secondary ? 'secondary' : 'primary'} className={`admin-button h-10! cursor-pointer rounded-[10px]! border px-3.5! font-admin! text-sm! ${secondary ? 'border-admin-border! bg-white! text-admin-blue! enabled:hover:bg-admin-soft!' : 'border-admin-blue! bg-admin-blue! text-white! enabled:hover:bg-admin-navy!'} ${className}`} {...props} />
}

export function ProductThumbnail({ name, src, large = false }) {
  const [failed, setFailed] = useState(false)
  const classes = `${large ? 'size-20 text-base' : 'size-10 text-[10px]'} inline-grid shrink-0 place-items-center overflow-hidden rounded-[9px] bg-admin-soft font-bold text-admin-blue`
  return src && !failed ? <img src={src} alt="" loading="lazy" className={`${classes} object-cover`} onError={() => setFailed(true)} /> : <span className={classes} aria-hidden="true">{productInitials(name)}</span>
}

export const PRODUCT_CONTROL = 'w-full rounded-[10px] border border-admin-border bg-white p-2.5 text-sm text-admin-text disabled:opacity-60'
