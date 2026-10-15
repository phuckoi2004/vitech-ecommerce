import { useState } from 'react'
import { formatDate, formatDateTime } from '../../lib/format.js'
import { returnStatusLabel, returnTypeLabel } from '../lib/returns.js'
import { ReturnButton, ReturnStatus } from './ReturnUi.jsx'
import Modal from './Modal.jsx'

function InfoRow({ label, children }) {
  return <div className="grid grid-cols-[170px_minmax(0,1fr)] text-[10px] leading-3"><dt className="font-medium text-admin-muted">{label}</dt><dd className="m-0 break-words whitespace-pre-wrap">{children ?? '—'}</dd></div>
}
export default function ReturnInformation({ item, assignedName }) {
  const [open, setOpen] = useState(false)
  const files = (item.Attachments ?? []).filter((file) => /^https:\/\//i.test(file.FileUrl) && ['Image', 'Video'].includes(file.FileType))
  const acceptedAt = (item.Histories ?? []).filter((history) => history.NewStatus === 'Approved').sort((a, b) => Date.parse(a.ChangedAt) - Date.parse(b.ChangedAt))[0]?.ChangedAt
  const decision = item.Status === 'Pending' ? 'Chờ nhân viên xác nhận' : item.Status === 'Cancelled' ? 'Khách hàng đã hủy yêu cầu' : returnStatusLabel(item.Status)
  return <>
    <section aria-label="Thông tin yêu cầu đổi trả" className="flex min-h-[735px] w-[565px] max-w-full flex-col gap-2.5 rounded-xl border border-admin-border bg-white p-[18px]">
      <h3 className="m-0 text-[13px] leading-4 font-semibold">Thông tin yêu cầu đổi trả</h3>
      <dl className="m-0 flex flex-col gap-2.5">
        <InfoRow label="Khách hàng">{item.CustomerName}</InfoRow>
        <InfoRow label="Đơn hàng">{item.OrderCode}</InfoRow>
        <InfoRow label="Sản phẩm"><span title={[item.Sku, item.VariantInfo].filter(Boolean).join(' • ') || undefined}>{item.ProductName || '—'}</span></InfoRow>
        <InfoRow label="Loại yêu cầu">{returnTypeLabel(item.RequestType)}</InfoRow>
        <InfoRow label="Thời điểm gửi yêu cầu">{formatDateTime(item.RequestedAt)}</InfoRow>
        <InfoRow label="Lý do đổi / trả">{item.Reason || '—'}</InfoRow>
      </dl>
      <div className="flex flex-col gap-1.5"><span className="text-[10px] leading-3 font-medium text-admin-muted">Minh chứng yêu cầu</span><button type="button" disabled={!files.length} aria-label="Xem minh chứng yêu cầu" onClick={() => setOpen(true)} className="flex h-[76px] w-[514px] max-w-full cursor-pointer items-center justify-center rounded-[9px] border border-admin-border bg-admin-page text-[10px] leading-3 font-medium text-admin-muted enabled:hover:bg-admin-soft disabled:cursor-default">{files.length ? 'Tệp minh chứng đính kèm (' + files.length + ')' : 'Chưa có tệp minh chứng đính kèm'}</button></div>
      <h3 className="m-0 text-[13px] leading-4 font-semibold">Xem xét yêu cầu</h3>
      <dl className="m-0 flex flex-col gap-2.5">
        <InfoRow label="Quyết định tiếp nhận">{decision}</InfoRow>
        <InfoRow label="Thời hạn đổi trả">{item.ReturnDeadline ? 'Đến ' + formatDate(item.ReturnDeadline) : 'Nhân viên xem xét yêu cầu'}</InfoRow>
        <InfoRow label="Nhân viên xử lý">{item.AssignedStaffName || assignedName || '—'}</InfoRow>
        <InfoRow label="Thời điểm tiếp nhận">{acceptedAt ? formatDateTime(acceptedAt) : '—'}</InfoRow>
        {item.DecisionReason && <InfoRow label="Lý do từ chối">{item.DecisionReason}</InfoRow>}
        {item.ReceivedAt && <InfoRow label="Thời điểm nhận hàng">{formatDateTime(item.ReceivedAt)}</InfoRow>}
      </dl>
      <div className="flex items-center gap-2 [&>span]:px-2 [&>span]:text-[9px]"><ReturnStatus status={item.Status} /></div>
    </section>
    <Modal open={open} title="Minh chứng yêu cầu đổi trả" onClose={() => setOpen(false)} variant="tailwind" wide footer={<ReturnButton secondary onClick={() => setOpen(false)}>Đóng</ReturnButton>}><div className="grid grid-cols-2 gap-4">{files.map((file) => <figure className="m-0" key={file.ServiceRequestAttachmentId}>{file.FileType === 'Image' ? <a href={file.FileUrl} target="_blank" rel="noopener noreferrer"><img src={file.FileUrl} alt="Ảnh minh chứng do khách hàng cung cấp" className="h-52 w-full rounded-lg bg-admin-page object-contain" /></a> : <video src={file.FileUrl} controls preload="metadata" className="h-52 w-full rounded-lg bg-admin-page" />}</figure>)}</div></Modal>
  </>
}
