import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import EmptyState from '../../components/shared/EmptyState.jsx'
import Pagination from '../../components/shared/Pagination.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { formatDate } from '../../lib/format.js'
import { listMyOrders } from '../../lib/order-api.js'
import { createWarranty, getWarrantyItems, uploadWarrantyImage } from '../../lib/warranty-api.js'
import { WarrantyBreadcrumb, WarrantyCard, WarrantyError, WarrantyLoading } from '../components/warranty/WarrantyCommon.jsx'
import { ACCOUNT_PATH, INFO_PATHS, ORDER_HISTORY_PATH, WARRANTY_HISTORY_PATH, warrantyRequestPath } from '../routes/paths.js'
import { RequestField as Field, RequestProduct as SelectedProduct, EvidenceImages } from '../components/service-request/RequestFormFields.jsx'
import './AccountPage.css'
import './WarrantyPage.css'

const PAGE_SIZE = 50

export default function WarrantyCreatePage() {
  const { user, withAccessToken } = useCustomerSession()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [page, setPage] = useState(1)
  const [orderId, setOrderId] = useState(params.get('order') ?? '')
  const [itemId, setItemId] = useState('')
  const [serialId, setSerialId] = useState('')
  const [issue, setIssue] = useState('')
  const [issueType, setIssueType] = useState('')
  const [occurredOn, setOccurredOn] = useState('')
  const [entries, setEntries] = useState([])
  const [consent, setConsent] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const submitLock = useRef(false)
  const errorBox = useRef(null)
  const [today] = useState(() => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }))
  const orders = useApiData(`warranty-orders:${user?.UserId}:${page}`, (signal) => withAccessToken((token) =>
    listMyOrders(token, { order_status: ['Delivered', 'Completed'], page, page_size: PAGE_SIZE }, { signal })))
  const items = useApiData(orderId ? `warranty-items:${user?.UserId}:${orderId}` : null,
    (signal) => withAccessToken((token) => getWarrantyItems(token, orderId, { signal })))
  const selectedOrder = orders.data?.Items.find((order) => order.OrderId === orderId)
  const item = items.data?.find((row) => row.OrderItemId === itemId)
  const serial = item?.Serials.find((row) => row.ProductSerialId === serialId)
  const eligibility = item?.IsSerialTracked ? serial : item
  const busy = saving || uploading
  const ready = eligibility?.CanRequest && issue.trim() && consent && !entries.some((entry) => !entry.attachment)

  useEffect(() => { document.title = 'Tạo yêu cầu bảo hành | VieTech' }, [])
  useEffect(() => { if (error) errorBox.current?.focus() }, [error])

  function selectOrder(id) {
    setOrderId(id); setItemId(''); setSerialId(''); setError('')
  }
  function selectItem(id) {
    setItemId(id)
    const next = items.data?.find((row) => row.OrderItemId === id)
    setSerialId(next?.Serials.length === 1 ? next.Serials[0].ProductSerialId : '')
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    if (submitLock.current || busy) return
    setError('')
    if (!item) return setError('Vui lòng chọn đơn hàng và sản phẩm cần bảo hành.')
    if (item.IsSerialTracked && !serial) return setError('Vui lòng chọn Serial/IMEI của thiết bị cần bảo hành.')
    if (!eligibility?.CanRequest) return setError(eligibility?.Reason || 'Sản phẩm chưa đủ điều kiện gửi yêu cầu.')
    if (!issue.trim()) return setError('Vui lòng mô tả tình trạng lỗi của sản phẩm.')
    if (occurredOn && occurredOn > today) return setError('Thời điểm phát sinh lỗi không được ở tương lai.')
    if (entries.some((entry) => !entry.attachment)) return setError('Hãy tải lại hoặc xóa ảnh chưa tải thành công trước khi gửi.')
    if (!consent) return setError('Vui lòng xác nhận thông tin và chính sách bảo hành trước khi gửi.')
    const description = [issueType && `Loại lỗi: ${issueType}`, occurredOn && `Phát sinh ngày: ${formatDate(occurredOn)}`,
      issue.trim()].filter(Boolean).join('\n')
    submitLock.current = true
    setSaving(true)
    try {
      const created = await withAccessToken((token) => createWarranty(token, {
        OrderItemId: item.OrderItemId, ProductSerialId: serial?.ProductSerialId ?? null,
        IssueDescription: description, Attachments: entries.map((entry) => entry.attachment),
      }))
      navigate(warrantyRequestPath(created.WarrantyRequestId), { replace: true, state: { warrantyCreated: created.WarrantyRequestId } })
    } catch (failure) {
      setError(failure.message)
      if (['warranty_request_open', 'serial_has_open_return', 'item_has_open_return', 'serial_not_with_customer'].includes(failure.code)) items.reload()
    } finally {
      submitLock.current = false
      setSaving(false)
    }
  }

  return <div className="cw-page shop-container">
    <WarrantyBreadcrumb current="Tạo yêu cầu bảo hành" />
    <div className="cw-heading"><div><h1>Tạo yêu cầu bảo hành</h1><p>Gửi thông tin sản phẩm cần bảo hành. VieTech sẽ kiểm tra và phản hồi yêu cầu của bạn.</p></div>
      <Link className="cw-secondary" to={WARRANTY_HISTORY_PATH}>← Quay lại bảo hành</Link></div>
    <ol className="cw-guide" aria-label="Các bước tạo yêu cầu">
      {['Chọn đơn hàng & sản phẩm', 'Mô tả tình trạng sản phẩm', 'Kiểm tra & gửi yêu cầu'].map((text, index) =>
        <li key={text} className={index === (ready ? 2 : item ? 1 : 0) ? 'is-active' : ''}><span>{index + 1}</span>{text}</li>)}
    </ol>
    {error && <p ref={errorBox} tabIndex={-1} className="cacc-notice" role="alert">{error}</p>}
    <form onSubmit={submit} noValidate>
      <div className="cw-columns"><div className="cw-main">
        <WarrantyCard id="warranty-product" number="01" title="Thông tin đơn hàng và sản phẩm">
          {orders.loading ? <WarrantyLoading /> : orders.error ? <WarrantyError message={orders.error} retry={orders.reload} />
            : !orders.data.Items.length && !orderId ? <EmptyState headingLevel={3} title="Chưa có đơn hàng đã giao" description="Bạn có thể tạo yêu cầu bảo hành cho sản phẩm trong đơn đã giao thành công."
              action={<Link className="cw-secondary" to={ORDER_HISTORY_PATH}>Xem lịch sử mua hàng</Link>} /> : <>
              <div className="cw-fields">
                <Field id="cw-order" label="Mã đơn hàng *"><select id="cw-order" className="cacc-input" value={orderId} disabled={busy} onChange={(event) => selectOrder(event.target.value)}>
                  <option value="">Chọn đơn hàng đã giao</option>
                  {orderId && !selectedOrder && <option value={orderId}>Đơn hàng đã chọn</option>}
                  {orders.data.Items.map((order) => <option key={order.OrderId} value={order.OrderId}>{order.OrderCode} · {formatDate(order.OrderedAt)}</option>)}
                </select></Field>
                <Field id="cw-item" label="Sản phẩm cần bảo hành *"><select id="cw-item" className="cacc-input" value={itemId} disabled={busy || !items.data} onChange={(event) => selectItem(event.target.value)}>
                  <option value="">Chọn sản phẩm cần bảo hành</option>
                  {items.data?.map((row) => <option key={row.OrderItemId} value={row.OrderItemId}>{row.ProductName} · {row.VariantInfo}</option>)}
                </select></Field>
              </div>
              <Pagination page={page} pageSize={PAGE_SIZE} total={orders.data.Total} label="Phân trang đơn hàng bảo hành" disabled={busy}
                onPageChange={(next) => { setPage(next); selectOrder('') }} />
            </>}
          {items.loading ? <WarrantyLoading /> : items.error ? <WarrantyError message={items.error} retry={items.reload} /> : null}
          {item && <>
            <SelectedProduct item={item} orderCode={selectedOrder?.OrderCode || 'Đơn hàng đã chọn'} />
            <div className="cw-fields">
              <Field id="cw-serial" label={item.IsSerialTracked ? 'Serial / IMEI *' : 'Serial / IMEI'}>
                {item.IsSerialTracked ? <select id="cw-serial" className="cacc-input" value={serialId} disabled={busy} onChange={(event) => setSerialId(event.target.value)}>
                  <option value="">Chọn thiết bị thuộc đơn hàng</option>
                  {item.Serials.map((row) => <option key={row.ProductSerialId} value={row.ProductSerialId}>{row.SerialNumber}</option>)}
                </select> : <input id="cw-serial" className="cacc-input" value="Sản phẩm không quản lý Serial/IMEI" readOnly />}
              </Field>
              <Field id="cw-period" label="Thời hạn bảo hành"><input id="cw-period" className="cacc-input" readOnly
                value={eligibility?.WarrantyEndDate ? `${formatDate(eligibility.WarrantyStartDate)} – ${formatDate(eligibility.WarrantyEndDate)}` : `${item.WarrantyMonths} tháng · Theo dữ liệu đơn hàng`} /></Field>
            </div>
            {(eligibility?.Reason || (!item.CanRequest && item.Reason)) && <p className="cacc-notice" role="status">{eligibility?.Reason || item.Reason}</p>}
          </>}
        </WarrantyCard>
        <WarrantyCard id="warranty-issue" number="02" title="Thông tin lỗi bảo hành">
          <div className="cw-fields">
            <Field id="cw-type" label="Loại lỗi"><select id="cw-type" className="cacc-input" value={issueType} disabled={busy} onChange={(event) => setIssueType(event.target.value)}>
              <option value="">Chọn loại lỗi của sản phẩm</option>{['Không lên nguồn', 'Màn hình / hiển thị', 'Pin / sạc', 'Âm thanh / kết nối', 'Lỗi khác'].map((value) => <option key={value}>{value}</option>)}
            </select></Field>
            <Field id="cw-date" label="Thời điểm phát sinh lỗi"><input id="cw-date" className="cacc-input" type="date" max={today} value={occurredOn} disabled={busy} onChange={(event) => setOccurredOn(event.target.value)} /></Field>
          </div>
          <Field id="cw-issue" label="Mô tả tình trạng lỗi *"><textarea id="cw-issue" className="cacc-input cw-textarea" required maxLength={5000} rows={5}
            placeholder="Vui lòng mô tả rõ tình trạng, thời điểm xảy ra lỗi và các thao tác đã thử…" value={issue} disabled={busy} onChange={(event) => setIssue(event.target.value)} /></Field>
        </WarrantyCard>
        <WarrantyCard id="warranty-evidence" number="03" title="Hình ảnh minh chứng (không bắt buộc)">
          <EvidenceImages entries={entries} setEntries={setEntries} busy={busy} setBusy={setUploading} withAccessToken={withAccessToken} uploadImage={uploadWarrantyImage} />
        </WarrantyCard>
      </div><aside className="cw-sidebar">
        <WarrantyCard id="warranty-contact" number="04" title="Thông tin liên hệ">
          <Field id="cw-name" label="Họ và tên"><input id="cw-name" className="cacc-input" readOnly value={user.FullName} /></Field>
          <Field id="cw-phone" label="Số điện thoại"><input id="cw-phone" className="cacc-input" readOnly value={user.PhoneNumber ?? ''} /></Field>
          <Field id="cw-email" label="Email"><input id="cw-email" className="cacc-input" readOnly value={user.Email ?? ''} /></Field>
          <p className="cw-help">VieTech sẽ liên hệ qua thông tin tài khoản để hướng dẫn gửi và nhận lại sản phẩm.</p>
          <Link className="cw-text-link" to={ACCOUNT_PATH}>Cập nhật thông tin liên hệ →</Link>
        </WarrantyCard>
        <WarrantyCard id="warranty-process" title="Quy trình tiếp nhận">
          <ol className="cw-process">{[['Gửi yêu cầu', 'Chọn sản phẩm, mô tả lỗi và gửi minh chứng.'], ['Tiếp nhận & kiểm tra', 'Nhân viên xác minh tình trạng sản phẩm.'], ['Xử lý & bàn giao', 'Theo dõi kết quả đến khi nhận lại sản phẩm.']].map(([title, text], index) =>
            <li key={title}><span>{index + 1}</span><div><strong>{title}</strong><p>{text}</p></div></li>)}</ol>
        </WarrantyCard>
        <div className="cw-policy"><h2>Lưu ý về chính sách</h2><ul>
          <li>Yêu cầu được kiểm tra theo thời hạn và điều kiện bảo hành của sản phẩm đã mua.</li>
          <li>Thời gian xử lý phụ thuộc tình trạng thực tế sau khi tiếp nhận.</li>
          <li>Bạn có thể theo dõi tiến trình tại mục Bảo hành và đổi trả.</li>
          <li>Chỉ có thể hủy yêu cầu mới, trước khi VieTech tiếp nhận sản phẩm.</li>
        </ul></div>
      </aside></div>
      <div className="cw-card cw-confirm">
        <label><input type="checkbox" checked={consent} disabled={busy} onChange={(event) => setConsent(event.target.checked)} />
          <span>Tôi xác nhận thông tin cung cấp là chính xác và đã đọc <Link to={INFO_PATHS.warranty} target="_blank" rel="noreferrer">chính sách bảo hành</Link> của VieTech.</span></label>
        <div className="cw-actions"><Link className="cw-secondary" to={WARRANTY_HISTORY_PATH}>Hủy bỏ</Link>
          <button className="cw-primary" type="submit" disabled={busy || !eligibility?.CanRequest}>{saving && <span className="spinner" />}{saving ? 'Đang gửi yêu cầu…' : 'Gửi yêu cầu bảo hành'}</button></div>
      </div>
    </form>
  </div>
}
