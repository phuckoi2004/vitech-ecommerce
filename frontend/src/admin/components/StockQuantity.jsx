export default function StockQuantity({ variant, detailed = false }) {
  const quantity = variant.StockQuantity
  const empty = quantity === 0
  const low = !empty && (variant.IsLowStock || (variant.MinStockLevel > 0 && quantity <= variant.MinStockLevel))
  const label = empty ? 'Hết hàng' : low ? 'Sắp hết' : 'Còn hàng'
  const color = empty ? 'text-admin-red' : low ? 'text-amber-700' : 'text-admin-muted'
  return <span className="inline-flex flex-col gap-1">
    <strong className={empty || low ? color : 'font-semibold'}>{quantity}{detailed ? ' sản phẩm' : ''}</strong>
    <span className={(detailed ? 'text-[11px] ' : 'text-[9px] ') + 'leading-[normal] font-medium ' + color}>{label}</span>
    {detailed && <span className="text-[11px] leading-[normal] font-normal text-admin-muted">Ngưỡng cảnh báo: {variant.MinStockLevel > 0 ? variant.MinStockLevel : 'Chưa bật'}</span>}
  </span>
}
