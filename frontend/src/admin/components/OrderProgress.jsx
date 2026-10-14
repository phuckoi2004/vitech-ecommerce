// Figma groups the backend's confirmation and completion states into four delivery stages.
const STAGES = { Pending: 0, Confirmed: 0, Processing: 1, Shipping: 2, Delivered: 3, Completed: 3 }

export default function OrderProgress({ status }) {
  const current = STAGES[status] ?? -1
  const labels = [status === 'Confirmed' ? 'Đã xác nhận' : 'Chờ xác nhận', 'Đang xử lý', 'Đang giao', status === 'Completed' ? 'Hoàn tất' : 'Đã giao']
  return <div className="flex min-h-20 items-center overflow-x-auto rounded-[14px] border border-admin-border bg-white px-[18px]">
    <ol aria-label="Tiến trình đơn hàng" className="m-0 flex list-none items-center gap-2 p-0">
      {labels.map((label, index) => <li key={index} aria-current={index === current ? 'step' : undefined} className="flex shrink-0 items-center gap-2">
        {index > 0 && <span aria-hidden="true" className={'mr-0 h-0.5 w-[70px] shrink-0 ' + (index <= current ? 'bg-admin-blue' : 'bg-admin-border')} />}
        <span aria-hidden="true" className={'inline-grid size-7 shrink-0 place-items-center rounded-full border text-[11px] font-bold ' + (index <= current ? 'border-admin-blue bg-admin-blue text-white' : 'border-admin-border bg-admin-page text-admin-muted')}>{index + 1}</span>
        <span className={'text-[11px] font-semibold whitespace-nowrap ' + (index <= current ? 'text-admin-blue' : 'text-admin-muted')}>{label}</span>
      </li>)}
    </ol>
  </div>
}
