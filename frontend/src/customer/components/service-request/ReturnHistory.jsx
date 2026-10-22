import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import EmptyState from '../../../components/shared/EmptyState.jsx'
import Money from '../../../components/shared/Money.jsx'
import Pagination from '../../../components/shared/Pagination.jsx'
import useApiData from '../../../hooks/useApiData.js'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { formatDateTime } from '../../../lib/format.js'
import { cancelReturn, getMyReturn, listMyReturns } from '../../../lib/return-api.js'
import { canCancelReturn, RETURN_STATUSES, returnStatusLabel, returnTypeLabel } from '../../../lib/returns.js'
import { orderPath, RETURN_CREATE_PATH, RETURN_HISTORY_PATH, returnRequestPath } from '../../routes/paths.js'
import { WarrantyError, WarrantyLoading } from '../warranty/WarrantyCommon.jsx'
import '../../pages/WarrantyPage.css'

const PAGE_SIZE = 6
const ReturnStatus = ({ item }) => <span className="cw-status" data-stage={item.Status}>{returnStatusLabel(item.Status)}</span>

function ReturnDetail({ id }) {
  const { user, withAccessToken } = useCustomerSession()
  const location = useLocation()
  const detail = useApiData(`customer-return:${user?.UserId}:${id}`, (signal) => withAccessToken((token) => getMyReturn(token, id, { signal })))
  const [confirming, setConfirming] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState('')
  const lock = useRef(false)
  useEffect(() => { document.title = 'Chi tiết đổi trả | VieTech' }, [])
  useEffect(() => {
    window.addEventListener('focus', detail.reload)
    return () => window.removeEventListener('focus', detail.reload)
  }, [detail.reload])

  async function cancel() {
    if (lock.current) return
    lock.current = true; setCancelling(true); setError('')
    try {
      await withAccessToken((token) => cancelReturn(token, id))
      setConfirming(false); detail.reload()
    } catch (failure) {
      setError(failure.message)
      if (failure.code === 'return_not_cancellable') { setConfirming(false); detail.reload() }
    } finally { lock.current = false; setCancelling(false) }
  }

  const item = detail.data
  return <>
    <Link className="cw-text-link" to={RETURN_HISTORY_PATH}>← Danh sách yêu cầu đổi trả</Link>
    {detail.loading ? <WarrantyLoading label="Đang tải yêu cầu đổi trả…" /> : detail.error ? <WarrantyError message={detail.error} retry={detail.reload} /> : <>
      {location.state?.returnCreated === id && <p className="cacc-notice is-success" role="status">Đã gửi yêu cầu đổi trả. VieTech sẽ xem xét và liên hệ để hướng dẫn bạn.</p>}
      <div className="cw-heading cw-detail-heading"><div><h1>Yêu cầu {item.RequestCode}</h1><p>Ngày gửi: {formatDateTime(item.RequestedAt)}</p></div><ReturnStatus item={item} /></div>
      <div className="cw-detail-actions"><button className="cw-secondary" type="button" onClick={detail.reload} disabled={cancelling}>Làm mới tiến trình</button>
        {item.OrderId && <Link className="cw-text-link" to={orderPath(item.OrderId)}>Xem đơn {item.OrderCode} →</Link>}</div>
      <dl className="cw-facts"><div><dt>Sản phẩm</dt><dd>{item.ProductName || 'Sản phẩm trong đơn hàng'}</dd></div>
        {item.VariantInfo && <div><dt>Phiên bản</dt><dd>{item.VariantInfo}</dd></div>}
        <div><dt>Hình thức yêu cầu</dt><dd>{returnTypeLabel(item.RequestType)} sản phẩm</dd></div><div><dt>Số lượng yêu cầu</dt><dd>{item.Quantity}</dd></div>
        <div><dt>Serial / IMEI</dt><dd>{item.SerialNumber || 'Không quản lý Serial/IMEI'}</dd></div>
        <div><dt>Tiếp nhận sản phẩm</dt><dd>{item.ReceivedAt ? formatDateTime(item.ReceivedAt) : 'Chưa ghi nhận nhận hàng'}</dd></div></dl>
      <section className="cw-detail-section"><h2>Lý do và tình trạng đã gửi</h2><p className="cw-description">{item.Reason}</p></section>
      {item.DecisionReason && <p className="cacc-notice" role="status">{item.DecisionReason}</p>}
      {item.CompensationApprovedAt && item.CompensationAmount != null && <div className="cw-result"><h2>Số tiền được xác nhận: <Money value={item.CompensationAmount} /></h2></div>}
      <div className="cw-policy cw-history-note"><p>VieTech cập nhật tiến trình sau mỗi bước xử lý. Việc hoàn tiền (nếu áp dụng) được xác nhận riêng; trạng thái hoàn tất yêu cầu không có nghĩa đã hoàn tiền.</p></div>
      {item.Attachments?.length > 0 && <section className="cw-detail-section"><h2>Minh chứng đã gửi</h2><ul className="cw-attachments">
        {item.Attachments.filter((entry) => /^https:\/\//i.test(entry.FileUrl)).map((entry, index) => <li key={entry.ServiceRequestAttachmentId}>
          <a href={entry.FileUrl} target="_blank" rel="noreferrer">{entry.FileType === 'Image' ? <img src={entry.FileUrl} alt={`Ảnh minh chứng ${index + 1}`} loading="lazy" /> : `Xem video minh chứng ${index + 1}`}</a></li>)}
      </ul></section>}
      <section className="cw-detail-section"><h2>Lịch sử xử lý</h2><ol className="cw-timeline">
        {item.Histories?.map((entry) => <li key={entry.ServiceRequestHistoryId}><time>{formatDateTime(entry.ChangedAt)}</time><p className="cw-description">{entry.Note || returnStatusLabel(entry.NewStatus)}</p></li>)}
      </ol></section>
      {error && <p className="cacc-notice" role="alert">{error}</p>}
      {canCancelReturn(item) && <div className="cw-cancel">{confirming ? <><p>Hủy yêu cầu {item.RequestCode}? Số lượng của yêu cầu sẽ được giải phóng để bạn có thể gửi lại nếu còn trong thời hạn.</p>
        <div className="cw-actions"><button className="cw-secondary" type="button" disabled={cancelling} onClick={() => setConfirming(false)}>Giữ yêu cầu</button>
          <button className="cw-primary" type="button" disabled={cancelling} onClick={cancel}>{cancelling ? 'Đang hủy…' : 'Xác nhận hủy'}</button></div></>
        : <button className="cw-secondary" type="button" onClick={() => setConfirming(true)}>Hủy yêu cầu đổi trả</button>}</div>}
    </>}
  </>
}

export default function ReturnHistory() {
  const { user, withAccessToken } = useCustomerSession()
  const [params, setParams] = useSearchParams()
  const requestId = params.get('request')
  const rawPage = Number(params.get('returnPage'))
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1
  const status = RETURN_STATUSES.some(([key]) => key === params.get('returnStatus')) ? params.get('returnStatus') : ''
  const list = useApiData(requestId ? null : `my-returns:${user?.UserId}:${page}:${status}`, (signal) =>
    withAccessToken((token) => listMyReturns(token, { page, page_size: PAGE_SIZE, status }, { signal })))
  useEffect(() => { if (!requestId) document.title = 'Đổi trả | VieTech' }, [requestId])
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

  if (requestId) return <ReturnDetail key={requestId} id={requestId} />
  return <>
    <div className="cw-heading cw-history-heading"><div><h1>Bảo hành và đổi trả</h1><p>Theo dõi yêu cầu đổi trả và phản hồi từ VieTech.</p></div>
      <Link className="cw-primary" to={RETURN_CREATE_PATH}>+ Tạo yêu cầu đổi trả</Link></div>
    <div className="cw-history-filter"><label htmlFor="cr-status-filter">Trạng thái đổi trả</label>
      <select id="cr-status-filter" className="cacc-input" value={status} onChange={(event) => update({ returnStatus: event.target.value, returnPage: '' })}>
        <option value="">Tất cả trạng thái</option>{RETURN_STATUSES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select><button type="button" className="cw-secondary" onClick={list.reload}>Làm mới</button></div>
    {list.loading ? <WarrantyLoading label="Đang tải yêu cầu đổi trả…" /> : list.error ? <WarrantyError message={list.error} retry={list.reload} /> : !list.data.Items.length ?
      <EmptyState headingLevel={2} title={list.data.Total > 0 ? 'Trang này không còn yêu cầu' : status ? 'Không có yêu cầu ở trạng thái này' : 'Bạn chưa có yêu cầu đổi trả'}
        description="Chọn sản phẩm từ đơn hàng đã giao để gửi yêu cầu cho VieTech." action={page > 1 || status ? <button type="button" className="cw-secondary" onClick={() => update({ returnPage: '', returnStatus: '' })}>Xem tất cả yêu cầu</button>
          : <Link className="cw-primary" to={RETURN_CREATE_PATH}>Tạo yêu cầu đổi trả</Link>} /> : <>
        <ul className="cw-requests" aria-label="Danh sách yêu cầu đổi trả">{list.data.Items.map((item) => <li key={item.ReturnRequestId}>
          <div className="cw-request-heading"><Link to={returnRequestPath(item.ReturnRequestId)}>{item.RequestCode}</Link><ReturnStatus item={item} /></div>
          <strong>{item.ProductName || 'Sản phẩm trong đơn hàng'}</strong>{item.VariantInfo && <p>{item.VariantInfo}</p>}
          <p>{returnTypeLabel(item.RequestType)} sản phẩm · Số lượng: {item.Quantity}</p>{item.SerialNumber && <p>Serial / IMEI: {item.SerialNumber}</p>}
          <p className="cw-request-issue">{item.Reason}</p><div className="cw-request-footer"><small>Ngày gửi: {formatDateTime(item.RequestedAt)}</small><Link className="cw-text-link" to={returnRequestPath(item.ReturnRequestId)}>Xem chi tiết →</Link></div>
        </li>)}</ul><Pagination page={page} pageSize={PAGE_SIZE} total={list.data.Total} label="Phân trang yêu cầu đổi trả" onPageChange={(next) => update({ returnPage: next > 1 ? next : '' })} />
      </>}
  </>
}
