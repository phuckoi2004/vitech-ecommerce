export { NewsButton as PaymentButton } from './NewsUi.jsx'
export { BannerStatus as PaymentStatus } from './BannerUi.jsx'

// The Figma actions use text glyphs, rather than SVG icons.
export function PaymentAction({ action, name, onClick }) {
  const deleting = action === 'delete', label = deleting ? 'Xóa' : 'Sửa'
  return <button type="button" aria-label={label + ' ' + name} title={label} onClick={onClick} className={'grid size-[34px] shrink-0 cursor-pointer place-items-center rounded-lg border bg-white p-0 font-semibold ' + (deleting ? 'border-admin-red text-sm text-admin-red hover:bg-red-50' : 'border-admin-border text-[13px] text-admin-blue hover:bg-admin-soft')}><span aria-hidden="true">{deleting ? '×' : '✎'}</span></button>
}
