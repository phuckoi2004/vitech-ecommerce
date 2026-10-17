export function SupportStatus({ status = 'waiting' }) {
  const label = status === 'active' ? 'Đang hỗ trợ' : status === 'closed' ? 'Đã kết thúc' : status === 'ai' ? 'Chat với AI' : 'Đang chờ'
  const color = status === 'active' ? 'bg-[#16a34a] text-white' : ['closed', 'ai'].includes(status) ? 'bg-admin-page text-admin-muted' : 'bg-[#f59e0b] text-admin-text'
  return <span className={'inline-block shrink-0 rounded-full px-2 py-[5px] text-[9px] leading-[11px] font-semibold ' + color}>{label}</span>
}

export function SupportError({ message, onRetry }) {
  return <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-[11px] text-admin-red"><span>{message}</span><button type="button" className="shrink-0 cursor-pointer underline" onClick={onRetry}>Thử lại</button></div>
}
