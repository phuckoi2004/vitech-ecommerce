import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import EmptyState from '../../../components/shared/EmptyState.jsx'
import Pagination from '../../../components/shared/Pagination.jsx'
import useApiData from '../../../hooks/useApiData.js'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { formatDateTime } from '../../../lib/format.js'
import { cancelWarranty, getMyWarranty, listMyWarranties } from '../../../lib/warranty-api.js'
import { canCancelWarranty, warrantyResultLabel, warrantyStageLabel } from '../../../lib/warranty.js'
import { orderPath, WARRANTY_CREATE_PATH, WARRANTY_HISTORY_PATH, warrantyRequestPath } from '../../routes/paths.js'
import { WarrantyError, WarrantyLoading, WarrantyStatus } from './WarrantyCommon.jsx'
import '../../pages/WarrantyPage.css'

const PAGE_SIZE = 6

function WarrantyDetail({ id }) {
  const { user, withAccessToken } = useCustomerSession()
  const location = useLocation()
  const detail = useApiData(`customer-warranty:${user?.UserId}:${id}`, (signal) => withAccessToken((token) => getMyWarranty(token, id, { signal })))
  const [confirming, setConfirming] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState('')
  const lock = useRef(false)

  useEffect(() => { document.title = 'Chi tiết bảo hành | VieTech' }, [])
  useEffect(() => {
    window.addEventListener('focus', detail.reload)
    return () => window.removeEventListener('focus', detail.reload)
  }, [detail.reload])

  async function cancel() {
    if (lock.current) return
    lock.current = true
    setCancelling(true)
    setError('')
    try {
      await withAccessToken((token) => cancelWarranty(token, id))
      setConfirming(false)
      detail.reload()
    } catch (failure) {
      setError(failure.message)
      if (failure.code === 'warranty_not_cancellable') { setConfirming(false); detail.reload() }
    } finally { lock.current = false; setCancelling(false) }
  }

  const item = detail.data
  return <>
    <Link className="cw-text-link" to={WARRANTY_HISTORY_PATH}>← Danh sách yêu cầu bảo hành</Link>
    {detail.loading ? <WarrantyLoading /> : detail.error ? <WarrantyError message={detail.error} retry={detail.reload} /> : <>
      {location.state?.warrantyCreated === id && <p className={`cacc-notice ${item.Status === 'Rejected' ? '' : 'is-success'}`} role="status">
        {item.Status === 'Rejected' ? 'Yêu cầu đã được ghi nhận nhưng không đủ điều kiện bảo hành. Xem lý do bên dưới.' : 'Đã gửi yêu cầu bảo hành. VieTech sẽ liên hệ để hướng dẫn tiếp nhận sản phẩm.'}</p>}
      <div className="cw-heading cw-detail-heading"><div><h1>Yêu cầu {item.RequestCode}</h1><p>Ngày gửi: {formatDateTime(item.RequestedAt)}</p></div><WarrantyStatus item={item} /></div>
      <div className="cw-detail-actions"><button className="cw-secondary" type="button" onClick={detail.reload} disabled={cancelling}>Làm mới tiến trình</button>
        {item.OrderId && <Link className="cw-text-link" to={orderPath(item.OrderId)}>Xem đơn {item.OrderCode} →</Link>}</div>
      <dl className="cw-facts"><div><dt>Sản phẩm</dt><dd>{item.ProductName || 'Sản phẩm trong đơn hàng'}</dd></div>
        {item.VariantInfo && <div><dt>Phiên bản</dt><dd>{item.VariantInfo}</dd></div>}
        <div><dt>Serial / IMEI</dt><dd>{item.SerialNumber || 'Không quản lý Serial/IMEI'}</dd></div>
        <div><dt>Tiếp nhận sản phẩm</dt><dd>{item.ReceivedAt ? formatDateTime(item.ReceivedAt) : 'Chờ tiếp nhận'}</dd></div></dl>
      <section className="cw-detail-section"><h2>Thông tin lỗi đã gửi</h2><p className="cw-description">{item.IssueDescription}</p></section>
      {item.EligibilityReason && <p className="cacc-notice" role="status">{item.EligibilityReason}</p>}
      {item.ResultApprovedAt && item.ResultType && <section className="cw-result"><h2>Kết quả bảo hành: {warrantyResultLabel(item.ResultType)}</h2>
        <p className="cw-description">{item.ResultNote}</p><small>Cập nhật: {formatDateTime(item.ResultApprovedAt)}</small></section>}
      {item.Attachments?.length > 0 && <section className="cw-detail-section"><h2>Minh chứng đã gửi</h2><ul className="cw-attachments">
        {item.Attachments.filter((entry) => /^https:\/\//i.test(entry.FileUrl)).map((entry, index) => <li key={entry.ServiceRequestAttachmentId}>
          <a href={entry.FileUrl} target="_blank" rel="noreferrer">{entry.FileType === 'Image'
            ? <img src={entry.FileUrl} alt={`Ảnh minh chứng ${index + 1}`} loading="lazy" /> : `Xem video minh chứng ${index + 1}`}</a></li>)}
      </ul></section>}
      <section className="cw-detail-section"><h2>Lịch sử xử lý</h2><ol className="cw-timeline">
        {item.Histories?.map((entry) => <li key={entry.ServiceRequestHistoryId}><time>{formatDateTime(entry.ChangedAt)}</time>
          <p className="cw-description">{entry.Note || warrantyStageLabel(entry.NewStatus)}</p></li>)}
      </ol></section>
      {error && <p className="cacc-notice" role="alert">{error}</p>}
      {canCancelWarranty(item) && <div className="cw-cancel">
        {confirming ? <><p>Hủy yêu cầu {item.RequestCode}? Bạn có thể tạo yêu cầu mới sau khi hủy.</p>
          <div className="cw-actions"><button className="cw-secondary" type="button" disabled={cancelling} onClick={() => setConfirming(false)}>Giữ yêu cầu</button>
            <button className="cw-primary" type="button" disabled={cancelling} onClick={cancel}>{cancelling ? 'Đang hủy…' : 'Xác nhận hủy'}</button></div></>
          : <button className="cw-secondary" type="button" onClick={() => setConfirming(true)}>Hủy yêu cầu bảo hành</button>}
      </div>}
    </>}
  </>
}

export default function WarrantyHistory() {
  const { user, withAccessToken } = useCustomerSession()
  const [params, setParams] = useSearchParams()
  const requestId = params.get('request')
  const rawPage = Number(params.get('warrantyPage'))
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1
  // API filters use database statuses. Stage labels within cards use the same derivation as admin.
  const status = ['New', 'HandedOver', 'Processing', 'Completed', 'Rejected', 'Cancelled'].includes(params.get('warrantyStatus')) ? params.get('warrantyStatus') : ''
  const list = useApiData(requestId ? null : `my-warranties:${user?.UserId}:${page}:${status}`, (signal) =>
    withAccessToken((token) => listMyWarranties(token, { page, page_size: PAGE_SIZE, status }, { signal })))

  useEffect(() => { if (!requestId) document.title = 'Bảo hành và đổi trả | VieTech' }, [requestId])
  useEffect(() => {
    if (requestId) return undefined
    window.addEventListener('focus', list.reload)
    return () => window.removeEventListener('focus', list.reload)
  }, [requestId, list.reload])

  function update(values) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(values)) {
        if (value) next.set(key, String(value))
        else next.delete(key)
      }
      return next
    })
  }

  if (requestId) return <WarrantyDetail key={requestId} id={requestId} />
  return <>
    <div className="cw-heading cw-history-heading"><div><h1>Bảo hành và đổi trả</h1><p>Theo dõi yêu cầu bảo hành và phản hồi từ VieTech.</p></div>
      <Link className="cw-primary" to={WARRANTY_CREATE_PATH}>+ Tạo yêu cầu bảo hành</Link></div>
    <div className="cw-history-filter"><label htmlFor="cw-status-filter">Trạng thái bảo hành</label>
      <select id="cw-status-filter" className="cacc-input" value={status} onChange={(event) => update({ warrantyStatus: event.target.value, warrantyPage: '' })}>
        <option value="">Tất cả trạng thái</option><option value="New">Mới / Đang kiểm tra</option><option value="Processing">Đang xử lý / Hoàn tất</option>
        <option value="HandedOver">Đã bàn giao trung tâm (yêu cầu cũ)</option><option value="Completed">Đã trả khách</option><option value="Rejected">Từ chối</option><option value="Cancelled">Đã hủy</option>
      </select><button type="button" className="cw-secondary" onClick={list.reload}>Làm mới</button></div>
    {list.loading ? <WarrantyLoading /> : list.error ? <WarrantyError message={list.error} retry={list.reload} /> : !list.data.Items.length ?
      <EmptyState headingLevel={2} title={list.data.Total > 0 ? 'Trang này không còn yêu cầu' : status ? 'Không có yêu cầu ở trạng thái này' : 'Bạn chưa có yêu cầu bảo hành'}
        description="Chọn sản phẩm từ đơn hàng đã giao để gửi yêu cầu cho VieTech."
        action={page > 1 || status ? <button type="button" className="cw-secondary" onClick={() => update({ warrantyPage: '', warrantyStatus: '' })}>Xem tất cả yêu cầu</button>
          : <Link className="cw-primary" to={WARRANTY_CREATE_PATH}>Tạo yêu cầu bảo hành</Link>} /> : <>
        <ul className="cw-requests" aria-label="Danh sách yêu cầu bảo hành">{list.data.Items.map((item) => <li key={item.WarrantyRequestId}>
          <div className="cw-request-heading"><Link to={warrantyRequestPath(item.WarrantyRequestId)}>{item.RequestCode}</Link><WarrantyStatus item={item} /></div>
          <strong>{item.ProductName || 'Sản phẩm trong đơn hàng'}</strong>{item.VariantInfo && <p>{item.VariantInfo}</p>}
          {item.SerialNumber && <p>Serial / IMEI: {item.SerialNumber}</p>}<p className="cw-request-issue">{item.IssueDescription}</p>
          <div className="cw-request-footer"><small>Ngày gửi: {formatDateTime(item.RequestedAt)}</small><Link className="cw-text-link" to={warrantyRequestPath(item.WarrantyRequestId)}>Xem chi tiết →</Link></div>
        </li>)}</ul>
        <Pagination page={page} pageSize={PAGE_SIZE} total={list.data.Total} label="Phân trang yêu cầu bảo hành" onPageChange={(next) => update({ warrantyPage: next > 1 ? next : '' })} />
      </>}
    <div className="cw-policy cw-history-note"><p>Tiến trình bảo hành được cập nhật sau mỗi bước xử lý. VieTech sẽ gửi thông báo khi có thay đổi hoặc kết quả.</p></div>
  </>
}
