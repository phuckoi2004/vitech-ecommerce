import editIcon from '../assets/supplier-edit.svg'
import unlockIcon from '../assets/shipping-unlock.svg'
import lockIcon from '../assets/shipping-lock.svg'

export { ProductButton as ShippingButton } from './ProductUi.jsx'

export function ShippingAction({ kind, active, name, onClick, disabled = false }) {
  const label = kind === 'edit' ? 'Sửa' : active ? 'Ngừng hoạt động' : 'Kích hoạt'
  return <button type="button" aria-label={label + ' ' + name} title={label} onClick={onClick} disabled={disabled} className={'inline-grid size-[35px] shrink-0 cursor-pointer place-items-center rounded-[9px] border bg-white p-0 enabled:hover:bg-admin-page disabled:cursor-not-allowed disabled:opacity-40 ' + (kind === 'edit' ? 'border-admin-border' : active ? 'border-[#16a34a]/10' : 'border-admin-red')}>
    <span className="relative block size-6 shrink-0" aria-hidden="true">
      <img src={kind === 'edit' ? editIcon : active ? unlockIcon : lockIcon} alt="" data-shipping-icon={kind === 'edit' ? 'edit' : active ? 'unlock' : 'lock'} className={'absolute max-w-none ' + (kind === 'edit' ? 'top-[2.416px] left-[3.906px]' : active ? 'top-[2.518px] left-[4px]' : 'top-[2.5px] left-[4px]')} />
    </span>
  </button>
}

export function ShippingStatus({ active }) {
  return <span className={'inline-block rounded-full px-2.5 py-1.5 text-[11px] leading-[normal] font-semibold whitespace-nowrap ' + (active ? 'bg-[#ecfdf5] text-[#16a34a]' : 'bg-[#fff1f2] text-admin-red')}>{active ? 'Đang hoạt động' : 'Ngừng hoạt động'}</span>
}
