import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import EmptyState from '../../components/shared/EmptyState.jsx'
import Pagination from '../../components/shared/Pagination.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { formatDate } from '../../lib/format.js'
import { listMyOrders } from '../../lib/order-api.js'
import { createReturn, getReturnItems, uploadReturnImage } from '../../lib/return-api.js'
import { RequestField as Field, RequestProduct, EvidenceImages } from '../components/service-request/RequestFormFields.jsx'
import { WarrantyBreadcrumb as Breadcrumb, WarrantyCard as RequestCard, WarrantyError, WarrantyLoading } from '../components/warranty/WarrantyCommon.jsx'
import { ACCOUNT_PATH, INFO_PATHS, ORDER_HISTORY_PATH, RETURN_HISTORY_PATH, returnRequestPath } from '../routes/paths.js'
import './AccountPage.css'
import './WarrantyPage.css'

const PAGE_SIZE = 50
const REASONS = ['Sản phẩm bị lỗi', 'Giao sai sản phẩm', 'Hư hỏng khi nhận hàng', 'Thiếu phụ kiện', 'Lý do khác']
const CONDITIONS = ['Còn hộp', 'Còn phụ kiện', 'Đã sử dụng', 'Còn tem/phiếu bảo hành']

export default function ReturnCreatePage() {
  const { user, withAccessToken } = useCustomerSession()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [page, setPage] = useState(1)
  const [orderId, setOrderId] = useState(params.get('order') ?? '')
  const [itemId, setItemId] = useState('')
  const [serialId, setSerialId] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [requestType, setRequestType] = useState('Return')
  const [reason, setReason] = useState('')
  const [description, setDescription] = useState('')
  const [usage, setUsage] = useState('')
  const [conditions, setConditions] = useState([])
  const [entries, setEntries] = useState([])
  const [consent, setConsent] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const lock = useRef(false)
  const errorBox = useRef(null)
  const orders = useApiData(`return-orders:${user?.UserId}:${page}`, (signal) => withAccessToken((token) =>
    listMyOrders(token, { order_status: ['Delivered', 'Completed'], page, page_size: PAGE_SIZE }, { signal })))
  const items = useApiData(orderId ? `return-items:${user?.UserId}:${orderId}` : null,
    (signal) => withAccessToken((token) => getReturnItems(token, orderId, { signal })))
  const selectedOrder = orders.data?.Items.find((row) => row.OrderId === orderId)
  const item = items.data?.find((row) => row.OrderItemId === itemId)
  const serial = item?.Serials.find((row) => row.ProductSerialId === serialId)
  const eligibility = item?.IsSerialTracked ? serial : item
  const busy = saving || uploading
  const count = Number(quantity)
  const validQuantity = Number.isSafeInteger(count) && count > 0 && count <= (item?.MaxQuantity ?? 0) && (!item?.IsSerialTracked || count === 1)
  const ready = eligibility?.CanRequest && validQuantity && reason && description.trim() && consent && entries.every((entry) => entry.attachment)

  useEffect(() => { document.title = 'Tạo yêu cầu đổi/trả | VieTech' }, [])
  useEffect(() => { if (error) errorBox.current?.focus() }, [error])

  function selectOrder(id) { setOrderId(id); setItemId(''); setSerialId(''); setQuantity('1'); setError('') }
  function selectItem(id) {
    setItemId(id)
    const next = items.data?.find((row) => row.OrderItemId === id)
    setSerialId(next?.Serials.length === 1 ? next.Serials[0].ProductSerialId : '')
    setQuantity('1'); setError('')
  }

  async function submit(event) {
    event.preventDefault()
    if (lock.current || busy) return
    setError('')
    if (!item) return setError('Vui lòng chọn đơn hàng và sản phẩm cần đổi/trả.')
    if (item.IsSerialTracked && !serial) return setError('Vui lòng chọn Serial/IMEI của thiết bị cần đổi/trả.')
    if (!eligibility?.CanRequest) return setError(eligibility?.Reason || item.Reason || 'Sản phẩm chưa đủ điều kiện gửi yêu cầu.')
    if (!validQuantity) return setError(`Số lượng phải là số nguyên từ 1 đến ${item.IsSerialTracked ? 1 : item.MaxQuantity}.`)
    if (!['Return', 'Exchange'].includes(requestType)) return setError('Vui lòng chọn hình thức đổi hoặc trả sản phẩm.')
    if (!reason) return setError('Vui lòng chọn lý do đổi/trả.')
    if (!description.trim()) return setError('Vui lòng mô tả chi tiết lý do đổi/trả và tình trạng sản phẩm.')
    if (entries.some((entry) => !entry.attachment)) return setError('Hãy tải lại hoặc xóa ảnh chưa tải thành công trước khi gửi.')
    if (!consent) return setError('Vui lòng xác nhận thông tin và chính sách đổi/trả trước khi gửi.')
    const details = [`Lý do: ${reason}`, description.trim(), usage && `Tình trạng sử dụng: ${usage}`,
      conditions.length && `Tình trạng sản phẩm và phụ kiện: ${conditions.join(', ')}`].filter(Boolean).join('\n')
    lock.current = true; setSaving(true)
    try {
      const created = await withAccessToken((token) => createReturn(token, {
        OrderItemId: item.OrderItemId, ProductSerialId: serial?.ProductSerialId ?? null, Quantity: count,
        RequestType: requestType, Reason: details, Attachments: entries.map((entry) => entry.attachment),
      }))
      navigate(returnRequestPath(created.ReturnRequestId), { replace: true, state: { returnCreated: created.ReturnRequestId } })
    } catch (failure) {
      setError(failure.message)
      if (['return_request_open', 'return_quantity_exceeded', 'serial_has_open_warranty', 'item_has_open_warranty', 'serial_not_with_customer', 'return_window_expired'].includes(failure.code)) items.reload()
    } finally { lock.current = false; setSaving(false) }
  }

  return <div className="cw-page shop-container">
    <Breadcrumb current="Tạo yêu cầu đổi/trả" backTo={RETURN_HISTORY_PATH} />
    <div className="cw-heading"><div><h1>Tạo yêu cầu đổi/trả</h1><p>Gửi yêu cầu đổi hoặc trả sản phẩm theo chính sách VieTech và theo dõi kết quả xử lý.</p></div>
      <Link className="cw-secondary" to={RETURN_HISTORY_PATH}>← Quay lại đổi/trả</Link></div>
    <ol className="cw-guide" aria-label="Các bước tạo yêu cầu đổi/trả">
      {['Chọn đơn hàng đã nhận', 'Chọn lý do & phương án xử lý', 'Kiểm tra & gửi yêu cầu'].map((text, index) =>
        <li key={text} className={index === (ready ? 2 : item ? 1 : 0) ? 'is-active' : ''}><span>{index + 1}</span>{text}</li>)}
    </ol>
    {error && <p ref={errorBox} tabIndex={-1} className="cacc-notice" role="alert">{error}</p>}
    <form onSubmit={submit} noValidate>
      <div className="cw-columns"><div className="cw-main">
        <RequestCard id="return-product" number="01" title="Thông tin đơn hàng và sản phẩm">
          {orders.loading ? <WarrantyLoading label="Đang tải đơn hàng…" /> : orders.error ? <WarrantyError message={orders.error} retry={orders.reload} />
            : !orders.data.Items.length && !orderId ? <EmptyState headingLevel={3} title="Chưa có đơn hàng đã giao" description="Bạn có thể tạo yêu cầu đổi/trả cho sản phẩm trong đơn đã giao thành công."
              action={<Link className="cw-secondary" to={ORDER_HISTORY_PATH}>Xem lịch sử mua hàng</Link>} /> : <>
              <div className="cw-fields">
                <Field id="cr-order" label="Mã đơn hàng *"><select id="cr-order" className="cacc-input" value={orderId} disabled={busy} onChange={(event) => selectOrder(event.target.value)}>
                  <option value="">Chọn đơn hàng đã giao</option>
                  {orderId && !selectedOrder && <option value={orderId}>Đơn hàng đã chọn</option>}
                  {orders.data.Items.map((row) => <option key={row.OrderId} value={row.OrderId}>{row.OrderCode} · {formatDate(row.OrderedAt)}</option>)}
                </select></Field>
                <Field id="cr-item" label="Sản phẩm đổi/trả *"><select id="cr-item" className="cacc-input" value={itemId} disabled={busy || !items.data} onChange={(event) => selectItem(event.target.value)}>
                  <option value="">Chọn sản phẩm cần đổi/trả</option>
                  {items.data?.map((row) => <option key={row.OrderItemId} value={row.OrderItemId}>{row.ProductName} · {row.VariantInfo}</option>)}
                </select></Field>
              </div>
              <Pagination page={page} pageSize={PAGE_SIZE} total={orders.data.Total} label="Phân trang đơn hàng đổi/trả" disabled={busy} onPageChange={(next) => { setPage(next); selectOrder('') }} />
            </>}
          {items.loading ? <WarrantyLoading label="Đang kiểm tra điều kiện đổi/trả…" /> : items.error ? <WarrantyError message={items.error} retry={items.reload} /> : null}
          {item && <>
            <RequestProduct item={item} orderCode={selectedOrder?.OrderCode || 'Đơn hàng đã chọn'} badge="CẦN KIỂM TRA" subtitle="Trạng thái đơn hàng: Đã nhận hàng" />
            <div className="cw-fields">
              <Field id="cr-quantity" label="Số lượng yêu cầu *"><input id="cr-quantity" className="cacc-input" type="number" min="1" step="1" max={item.MaxQuantity}
                value={quantity} readOnly={item.IsSerialTracked} disabled={busy} onChange={(event) => setQuantity(event.target.value)} /></Field>
              <Field id="cr-serial" label={item.IsSerialTracked ? 'Serial / IMEI *' : 'Serial / IMEI'}>
                {item.IsSerialTracked ? <select id="cr-serial" className="cacc-input" value={serialId} disabled={busy} onChange={(event) => setSerialId(event.target.value)}>
                  <option value="">Chọn thiết bị thuộc đơn hàng</option>{item.Serials.map((row) => <option key={row.ProductSerialId} value={row.ProductSerialId}>{row.SerialNumber}</option>)}
                </select> : <input id="cr-serial" className="cacc-input" value="Sản phẩm không quản lý Serial/IMEI" readOnly />}
              </Field>
            </div>
            <p className="cw-help">{item.IsSerialTracked ? 'Mỗi yêu cầu áp dụng cho một thiết bị theo Serial/IMEI đã chọn.' : `Số lượng còn có thể yêu cầu: ${item.MaxQuantity}/${item.Quantity}.`}
              {item.ReturnDeadline && <> Hạn gửi yêu cầu: <strong>{formatDate(item.ReturnDeadline)}</strong>{item.WindowDays && ` (${item.WindowDays} ngày tính từ ngày giao hàng).`}</>}</p>
            {(eligibility?.Reason || (!item.CanRequest && item.Reason)) && <p className="cacc-notice" role="status">{eligibility?.Reason || item.Reason}</p>}
          </>}
        </RequestCard>
        <RequestCard id="return-reason" number="02" title="Thông tin yêu cầu đổi/trả">
          <fieldset className="cr-request-types" disabled={busy}><legend>Hình thức yêu cầu *</legend>
            {[['Exchange', 'Đổi sản phẩm', 'Đề nghị đổi cùng phiên bản đã mua'], ['Return', 'Trả hàng', 'Đề nghị trả lại sản phẩm đã nhận']].map(([value, title, text]) =>
              <label key={value} className={requestType === value ? 'is-selected' : ''}><input type="radio" name="return-request-type" value={value} checked={requestType === value} onChange={() => setRequestType(value)} />
                <span><strong>{title}</strong><small>{text}</small></span></label>)}
          </fieldset>
          <div className="cw-fields">
            <Field id="cr-reason" label="Lý do đổi/trả *"><select id="cr-reason" className="cacc-input" value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)}>
              <option value="">Chọn lý do đổi/trả</option>{REASONS.map((value) => <option key={value}>{value}</option>)}</select></Field>
            <Field id="cr-usage" label="Tình trạng sử dụng"><select id="cr-usage" className="cacc-input" value={usage} disabled={busy} onChange={(event) => setUsage(event.target.value)}>
              <option value="">Chọn tình trạng sản phẩm</option>{['Chưa sử dụng', 'Đã sử dụng', 'Không hoạt động'].map((value) => <option key={value}>{value}</option>)}</select></Field>
          </div>
          <Field id="cr-description" label="Mô tả chi tiết lý do đổi/trả *"><textarea id="cr-description" className="cacc-input cw-textarea" rows={5} maxLength={5000} required
            placeholder="Mô tả vấn đề gặp phải, tình trạng sản phẩm và đề xuất xử lý của bạn…" value={description} disabled={busy} onChange={(event) => setDescription(event.target.value)} /></Field>
          <fieldset className="cw-accessories" disabled={busy}><legend>Tình trạng sản phẩm và phụ kiện</legend>
            {CONDITIONS.map((value) => <label key={value}><input type="checkbox" checked={conditions.includes(value)} onChange={(event) =>
              setConditions((current) => event.target.checked ? [...current, value] : current.filter((entry) => entry !== value))} />{value}</label>)}
          </fieldset>
        </RequestCard>
        <RequestCard id="return-evidence" number="03" title="Hình ảnh minh chứng (không bắt buộc)">
          <EvidenceImages entries={entries} setEntries={setEntries} busy={busy} setBusy={setUploading} withAccessToken={withAccessToken} uploadImage={uploadReturnImage} />
        </RequestCard>
        <RequestCard id="return-resolution" number="04" title="Phương án xử lý mong muốn">
          <div className="cw-policy"><strong>{requestType === 'Exchange' ? 'Bạn đang chọn: Đổi sản phẩm' : 'Bạn đang chọn: Trả hàng'}</strong>
            <p>{requestType === 'Exchange' ? 'Đề nghị đổi sản phẩm cùng phiên bản đã mua. VieTech sẽ kiểm tra và xác nhận phương án cụ thể với bạn.'
              : 'Đề nghị trả lại sản phẩm đã chọn. VieTech sẽ kiểm tra điều kiện và phản hồi phương án xử lý.'}</p></div>
          <p className="cw-help">Việc hoàn tiền (nếu áp dụng) được VieTech xác nhận riêng sau khi kiểm tra. Trạng thái hoàn tất yêu cầu không phải xác nhận đã hoàn tiền.</p>
        </RequestCard>
      </div><aside className="cw-sidebar">
        <RequestCard id="return-contact" number="05" title="Thông tin liên hệ">
          <Field id="cr-name" label="Họ và tên"><input id="cr-name" className="cacc-input" readOnly value={user.FullName} /></Field>
          <Field id="cr-phone" label="Số điện thoại"><input id="cr-phone" className="cacc-input" readOnly value={user.PhoneNumber ?? ''} /></Field>
          <Field id="cr-email" label="Email"><input id="cr-email" className="cacc-input" readOnly value={user.Email ?? ''} /></Field>
          <p className="cw-help">VieTech sẽ liên hệ qua thông tin tài khoản để hướng dẫn gửi và nhận lại sản phẩm.</p>
          <Link className="cw-text-link" to={ACCOUNT_PATH}>Cập nhật thông tin liên hệ →</Link>
        </RequestCard>
        <RequestCard id="return-process" title="Quy trình xử lý">
          <ol className="cw-process">{[['Gửi yêu cầu', 'Cung cấp thông tin và minh chứng.'], ['Đối chiếu chính sách', 'Kiểm tra điều kiện và tình trạng sản phẩm.'], ['Thông báo kết quả', 'VieTech cập nhật tiến trình và phản hồi phương án xử lý.']].map(([title, text], index) =>
            <li key={title}><span>{index + 1}</span><div><strong>{title}</strong><p>{text}</p></div></li>)}</ol>
        </RequestCard>
        <div className="cw-policy"><h2>Điều kiện đổi/trả</h2><ul>
          <li>Yêu cầu được xét theo thời hạn, tình trạng và chính sách của sản phẩm đã mua.</li>
          <li>Gửi yêu cầu trong hạn được hiển thị sau khi chọn sản phẩm.</li>
          <li>VieTech sẽ kiểm tra thực tế trước khi xác nhận phương án xử lý.</li>
          <li>Theo dõi kết quả tại mục Bảo hành và đổi trả. Chỉ có thể hủy khi yêu cầu đang chờ xem xét.</li>
        </ul></div>
      </aside></div>
      <div className="cw-card cw-confirm">
        <label><input type="checkbox" checked={consent} disabled={busy} onChange={(event) => setConsent(event.target.checked)} />
          <span>Tôi cam kết cung cấp thông tin đúng tình trạng sản phẩm và đồng ý với <Link to={INFO_PATHS.returns} target="_blank" rel="noreferrer">chính sách đổi/trả</Link> VieTech.</span></label>
        <div className="cw-actions"><Link className="cw-secondary" to={RETURN_HISTORY_PATH}>Hủy bỏ</Link>
          <button className="cw-primary" type="submit" disabled={busy || !eligibility?.CanRequest}>{saving && <span className="spinner" />}{saving ? 'Đang gửi yêu cầu…' : 'Gửi yêu cầu đổi/trả'}</button></div>
      </div>
    </form>
  </div>
}
