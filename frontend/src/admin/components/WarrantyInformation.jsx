import { useState } from 'react'
import { formatDate, formatDateTime } from '../../lib/format.js'
import { warrantySerialLabel } from '../lib/warranties.js'
import Modal from './Modal.jsx'
import { WarrantyButton } from './WarrantyUi.jsx'

function InformationRow({ label, children }) {
  return <div className="grid grid-cols-[185px_minmax(0,1fr)] text-[11px] leading-[13px] font-medium"><dt className="text-admin-muted">{label}</dt><dd className="m-0 break-words whitespace-pre-wrap">{children ?? '—'}</dd></div>
}

export default function WarrantyInformation({ item, assignedName, children }) {
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const files = (item.Attachments ?? []).filter((file) => /^https:\/\//i.test(file.FileUrl) && ['Image', 'Video'].includes(file.FileType))
  const images = files.filter((file) => file.FileType === 'Image').length
  const videos = files.filter((file) => file.FileType === 'Video').length
  const evidenceLabel = [images && images + ' ảnh', videos && videos + ' video'].filter(Boolean).join(' • ')
  const eligibility = ({ Pending: 'Chờ kiểm tra', Eligible: 'Đủ điều kiện bảo hành', Ineligible: 'Không đủ điều kiện bảo hành' })[item.EligibilityStatus] ?? '—'
  return <>
    <section aria-label="Thông tin yêu cầu bảo hành" className="grid min-h-[537px] grid-cols-[510px_minmax(0,1fr)] items-start rounded-[14px] border border-admin-border bg-white p-[18px]">
      <div className="flex min-w-0 flex-col gap-[11px] pr-2">
        <h3 className="m-0 text-sm leading-[17px] font-semibold">Thông tin yêu cầu</h3>
        <dl className="m-0 flex flex-col gap-[11px]">
          <InformationRow label="Khách hàng">{item.CustomerName}</InformationRow>
          <InformationRow label="Đơn hàng">{item.OrderCode}</InformationRow>
          <InformationRow label="Sản phẩm">{item.ProductName}</InformationRow>
          <InformationRow label="Serial / IMEI"><span title={item.SerialNumber || undefined}>{warrantySerialLabel(item.SerialNumber)}</span></InformationRow>
          <InformationRow label="Thời điểm gửi">{formatDateTime(item.RequestedAt)}</InformationRow>
          <InformationRow label="Mô tả lỗi">{item.IssueDescription || '—'}</InformationRow>
        </dl>
        <h3 className="m-0 text-sm leading-[17px] font-semibold">Kiểm tra điều kiện bảo hành</h3>
        <dl className="m-0 flex flex-col gap-[11px]">
          <InformationRow label="Kết quả điều kiện">{eligibility}</InformationRow>
          <InformationRow label="Thời hạn bảo hành">{item.WarrantyEndDate ? 'Đến ' + formatDate(item.WarrantyEndDate) : '—'}</InformationRow>
          <InformationRow label="Nhân viên xử lý">{item.AssignedStaffName || assignedName || '—'}</InformationRow>
          <InformationRow label="Thời điểm tiếp nhận">{item.ReceivedAt ? formatDateTime(item.ReceivedAt) : '—'}</InformationRow>
          {item.EligibilityReason && <InformationRow label={item.Status === 'Rejected' ? 'Lý do từ chối' : 'Ghi nhận điều kiện'}>{item.EligibilityReason}</InformationRow>}
        </dl>
      </div>
      <div className="-mt-2 flex w-[510px] max-w-full flex-col gap-[7px]">
        <span className="text-[11px] leading-[13px] font-medium text-admin-muted">Ảnh / video minh chứng</span>
        <button type="button" aria-label="Xem ảnh / video minh chứng" disabled={!files.length} onClick={() => setEvidenceOpen(true)} className="flex h-[76px] cursor-pointer items-center justify-center rounded-[9px] border border-admin-border bg-admin-page text-[11px] leading-[13px] font-medium text-admin-muted enabled:hover:bg-admin-soft disabled:cursor-default">{evidenceLabel || 'Chưa có ảnh / video minh chứng'}</button>
        {children}
      </div>
    </section>
    <Modal open={evidenceOpen} title="Ảnh / video minh chứng" onClose={() => setEvidenceOpen(false)} variant="tailwind" wide footer={<WarrantyButton secondary onClick={() => setEvidenceOpen(false)}>Đóng</WarrantyButton>}>
      <div className="grid grid-cols-2 gap-4">{files.map((file) => <figure className="m-0" key={file.ServiceRequestAttachmentId}>{file.FileType === 'Image' ? <a href={file.FileUrl} target="_blank" rel="noopener noreferrer"><img src={file.FileUrl} alt="Ảnh minh chứng do khách hàng cung cấp" className="h-52 w-full rounded-lg bg-admin-page object-contain" /></a> : <video src={file.FileUrl} controls preload="metadata" className="h-52 w-full rounded-lg bg-admin-page" />}</figure>)}</div>
    </Modal>
  </>
}
