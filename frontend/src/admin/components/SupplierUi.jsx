import detailIcon from '../assets/supplier-detail.svg'
import editIcon from '../assets/supplier-edit.svg'
import trashIcon from '../assets/supplier-trash.svg'
import { ProductButton } from './ProductUi.jsx'

export function SupplierButton({ secondary = false, className = '', ...props }) {
  return <ProductButton secondary={secondary} className={'h-[33px]! rounded-[9px]! px-[13px]! text-[11px]! ' + (secondary ? 'text-admin-text! ' : 'border-admin-red! bg-admin-red! enabled:hover:bg-admin-red/90! ') + className} {...props} />
}

export function SupplierStatus({ active }) {
  return <span className={'inline-block rounded-full px-2 py-[5px] text-[9px] leading-[normal] font-semibold whitespace-nowrap text-white ' + (active ? 'bg-[#16a34a]' : 'bg-admin-red')}>{active ? 'Hoạt động' : 'Ẩn'}</span>
}

export function SupplierAction({ kind, name, onClick, disabled = false, disabledTitle = 'Nhà cung cấp đã ẩn' }) {
  const label = { view: 'Chi tiết', edit: 'Sửa', delete: 'Xóa' }[kind]
  return <button type="button" aria-label={label + ' ' + name} title={disabled ? disabledTitle : label} onClick={onClick} disabled={disabled} className={'inline-grid size-[35px] shrink-0 cursor-pointer place-items-center rounded-[9px] border bg-white p-0 enabled:hover:bg-admin-page disabled:cursor-not-allowed disabled:opacity-40 ' + (kind === 'delete' ? 'border-admin-red' : 'border-admin-border')}>
    <span className="relative block size-6 shrink-0" aria-hidden="true">
      {kind === 'view' ? <img src={detailIcon} width="18" height="18" alt="" data-supplier-icon="view" className="absolute top-[3px] left-[3px] max-w-none" />
        : kind === 'edit' ? <img src={editIcon} alt="" data-supplier-icon="edit" className="absolute top-[2.416px] left-[3.906px] max-w-none" />
          : <img src={trashIcon} width="24" height="24" alt="" data-supplier-icon="delete" className="absolute top-0 left-0 max-w-none" />}
    </span>
  </button>
}
