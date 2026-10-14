import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import { listPaymentMethods, listShippingMethods } from '../../lib/catalog-api.js'
import { formatMoney } from '../../lib/format.js'
import { ACCOUNT_PATH, CART_PATH, CHAT_PATH, INFO_PATHS, SEARCH_PATH } from '../routes/paths.js'
import './ShoppingPages.css'

function Methods({ shipping = false }) {
  const source = useApiData(shipping ? 'info-shipping' : 'info-payment', (signal) =>
    shipping ? listShippingMethods({ signal }) : listPaymentMethods({ signal }))
  if (source.loading) return <LoadingState />
  if (source.error) return <ErrorState message={source.error} onRetry={source.reload} />
  if (!source.data.length) return <p>Thông tin {shipping ? 'vận chuyển' : 'thanh toán'} đang được cập nhật.</p>
  return <ul>{source.data.map((method) => <li key={method.ShippingMethodId ?? method.PaymentMethodId}>
    <strong>{method.Name}</strong>{method.Description && <p>{method.Description}</p>}
    {shipping && <p>Phí cơ bản: {formatMoney(method.BaseFee)} · Thời gian dự kiến: {method.EstimatedDays === 0 ? 'Trong ngày' : `${method.EstimatedDays} ngày`}</p>}
  </li>)}</ul>
}

// Describes the available customer features. Unknown store/contact details remain explicitly unpublished.
const PAGES = {
  about: { title: 'Giới thiệu VieTech', paragraphs: [
    'VieTech là cửa hàng trực tuyến dành cho các sản phẩm công nghệ. Bạn có thể tìm theo tên sản phẩm, danh mục hoặc thương hiệu.',
    'Thông tin phiên bản, giá bán, tình trạng còn hàng và thời hạn bảo hành được trình bày trên trang sản phẩm.',
  ], links: [['Khám phá sản phẩm', SEARCH_PATH]] },
  contact: { title: 'Liên hệ', paragraphs: [
    'Bạn cần hỗ trợ chọn sản phẩm hoặc có thắc mắc về đơn hàng? Hãy trao đổi với nhân viên VieTech qua chat.',
    'Thông tin hotline, email và địa chỉ liên hệ đang được cập nhật.',
  ], links: [['Chat với nhân viên', CHAT_PATH]] },
  stores: { title: 'Hệ thống cửa hàng', paragraphs: [
    'Thông tin địa chỉ và thời gian mở cửa của các cửa hàng đang được cập nhật.',
    'Bạn có thể tiếp tục tìm sản phẩm trực tuyến hoặc liên hệ nhân viên để được hỗ trợ.',
  ], links: [['Xem sản phẩm', SEARCH_PATH], ['Liên hệ', INFO_PATHS.contact]] },
  buyingGuide: { title: 'Hướng dẫn mua hàng', paragraphs: [
    'Tìm sản phẩm bằng ô tìm kiếm, danh mục hoặc thương hiệu. Mở trang sản phẩm để xem mô tả, thông số và thời hạn bảo hành.',
    'Chọn phiên bản phù hợp rồi thêm vào giỏ hàng. Bạn cần đăng nhập bằng tài khoản khách hàng để quản lý giỏ của mình.',
    'Trong giỏ hàng, bạn có thể chọn sản phẩm, cập nhật số lượng và xóa sản phẩm không cần mua. Giá và tồn kho được kiểm tra lại khi đặt hàng.',
  ], links: [['Tìm sản phẩm', SEARCH_PATH], ['Xem giỏ hàng', CART_PATH]] },
  payment: { title: 'Thanh toán', paragraphs: [
    'Các phương thức đang được cửa hàng hỗ trợ được liệt kê bên dưới. Hãy làm theo hướng dẫn của phương thức được chọn và kiểm tra đúng số tiền, nội dung chuyển khoản.',
    'Trạng thái thanh toán được ghi nhận sau khi kết quả thanh toán được xác nhận. Nếu có thắc mắc về một giao dịch, hãy cung cấp thông tin đơn hàng cho nhân viên.',
  ], methods: 'payment', links: [['Liên hệ hỗ trợ', INFO_PATHS.contact]] },
  shipping: { title: 'Vận chuyển', paragraphs: [
    'Phương thức vận chuyển, phí cơ bản và thời gian dự kiến được cập nhật bên dưới. Phí cuối cùng được xác nhận theo thông tin đặt hàng.',
    'Thời gian giao thực tế có thể phụ thuộc địa chỉ nhận hàng và tình trạng xử lý đơn. Liên hệ nhân viên nếu bạn cần hỗ trợ.',
  ], methods: 'shipping', links: [['Liên hệ hỗ trợ', INFO_PATHS.contact]] },
  afterSales: { title: 'Đổi trả & bảo hành', paragraphs: [
    'Khi cần hỗ trợ sau mua hàng, hãy cung cấp mã đơn, sản phẩm, tình trạng gặp phải và serial/IMEI nếu thiết bị có quản lý serial.',
    'Nhân viên sẽ kiểm tra thông tin mua hàng, thời hạn và điều kiện áp dụng trước khi tiếp nhận yêu cầu.',
  ], links: [['Chính sách đổi trả', INFO_PATHS.returns], ['Chính sách bảo hành', INFO_PATHS.warranty], ['Liên hệ hỗ trợ', INFO_PATHS.contact]] },
  privacy: { title: 'Chính sách bảo mật', paragraphs: [
    'Thông tin tài khoản, địa chỉ, đơn hàng và nội dung hỗ trợ được sử dụng để cung cấp dịch vụ mua hàng, giao hàng và chăm sóc khách hàng.',
    'Các dữ liệu riêng như địa chỉ, giỏ hàng, thông báo và hội thoại yêu cầu đăng nhập và được giới hạn theo tài khoản của bạn.',
    'Bạn có thể xem và cập nhật thông tin cá nhân trong trang tài khoản. Vui lòng giữ kín mật khẩu và mã xác minh.',
  ], links: [['Tài khoản của bạn', ACCOUNT_PATH], ['Liên hệ', INFO_PATHS.contact]] },
  terms: { title: 'Điều khoản sử dụng', paragraphs: [
    'Cung cấp thông tin tài khoản chính xác và bảo vệ thông tin đăng nhập. Kiểm tra phiên bản, giá và thông tin sản phẩm trước khi mua.',
    'Giá bán, tình trạng còn hàng và điều kiện ưu đãi có thể được cập nhật. Giá, tồn kho và tổng tiền được hệ thống kiểm tra lại khi đặt hàng.',
    'Yêu cầu hủy đơn, đổi trả và bảo hành được xử lý theo trạng thái đơn và điều kiện áp dụng. Hãy liên hệ nhân viên khi cần hỗ trợ.',
  ], links: [['Chính sách bảo mật', INFO_PATHS.privacy], ['Đổi trả & bảo hành', INFO_PATHS.afterSales]] },
  returns: { title: 'Chính sách đổi trả', paragraphs: [
    'Yêu cầu đổi trả cần gắn với sản phẩm trong đơn đã giao của bạn, đáp ứng thời hạn và điều kiện áp dụng của cửa hàng.',
    'Nhân viên kiểm tra thông tin đơn, số lượng, serial/IMEI và tình trạng thực tế của sản phẩm trước khi quyết định xử lý. Khoản hoàn tiền được xác nhận theo kết quả xử lý yêu cầu.',
  ], links: [['Hướng dẫn hỗ trợ sau mua', INFO_PATHS.afterSales], ['Liên hệ nhân viên', INFO_PATHS.contact]] },
  warranty: { title: 'Chính sách bảo hành', paragraphs: [
    'Thời hạn bảo hành được ghi trên trang sản phẩm. Việc tiếp nhận phụ thuộc thông tin mua hàng, thời hạn và kết quả kiểm tra điều kiện bảo hành.',
    'Khi cần bảo hành, hãy cung cấp thông tin đơn hàng, mô tả tình trạng và serial/IMEI của thiết bị nếu có.',
  ], links: [['Tìm sản phẩm', SEARCH_PATH], ['Liên hệ nhân viên', INFO_PATHS.contact]] },
}

export default function InfoPage({ page }) {
  const content = PAGES[page]
  useEffect(() => { document.title = `${content.title} – VieTech` }, [content.title])
  return <div className="shopping-page info-page">
    <h1>{content.title}</h1>
    <section className="shopping-panel info-content">
      {content.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      {content.methods && <Methods shipping={content.methods === 'shipping'} />}
    </section>
    <nav className="shopping-actions" aria-label="Thông tin liên quan">
      {content.links.map(([label, to]) => <Link key={to} to={to}>{label}</Link>)}
    </nav>
  </div>
}
