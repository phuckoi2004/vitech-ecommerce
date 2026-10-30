import { useId } from 'react'
import { Link } from 'react-router-dom'
import { productPath } from '../routes/paths.js'
import StoreImage from './StoreImage.jsx'
import { compatibilityLabel, compatibilityStrings as strings, isCompatibility } from './ai-compatibility.js'
import { customerAiText } from './ai-customer-wording.js'

const symbols = { compatible: '✓', incompatible: '!', requires_adapter: '↗', unknown: '?' }
const connectors = { hdmi: 'HDMI', displayport: 'DisplayPort', usb_c: 'USB-C', thunderbolt: 'Thunderbolt' }

const MODE_CRITERIA = ['resolution', 'refresh_rate', 'signal_mode']

function Status({ status, basis, modeBasis, requested = true }) {
  return <span className={`ai-compatibility-status is-${requested ? status : 'unrequested'}`}>
    <span aria-hidden="true">{requested ? symbols[status] : '—'}</span>
    {requested ? compatibilityLabel(status, basis, modeBasis) : 'Chưa yêu cầu'}
  </span>
}

function Lines({ items }) {
  const lines = strings(items)
  return lines.length > 0 ? <ul>{lines.map((line, index) => <li key={index}>{line}</li>)}</ul> : null
}

export default function AiCompatibility({ compatibility: result, onLoad }) {
  const titleId = useId()
  if (!isCompatibility(result)) return null
  const request = result.Request ?? {}
  const width = Number(request.Width), height = Number(request.Height), hz = Number(request.RefreshHz)
  // The connector and direct-only choices change the verdict, so they are shown with the resolution and Hz.
  const target = [width > 0 && height > 0 && `${width}×${height}`, hz > 0 && `${hz} Hz`,
    Object.hasOwn(connectors, request.SourceConnector) && `qua cổng ${connectors[request.SourceConnector]} của laptop`,
    request.DirectOnly === true && 'chỉ kết nối trực tiếp, không dùng bộ chuyển đổi'].filter(Boolean).join(' · ')
  return <section className="ai-compatibility" aria-labelledby={titleId}>
    <h4 id={titleId}>VIETECH AI – KIỂM TRA TƯƠNG THÍCH</h4>
    <div className="ai-compatibility-overview"><Status status={result.Status} basis={result.Basis} modeBasis={result.ModeBasis} />
      {result.CheckType === 'laptop_video_output' && <p>Kiểm tra chức năng xuất hình của laptop. Chọn thêm màn hình để kiểm tra toàn bộ kết nối.</p>}
      {target && <p>Yêu cầu cần kiểm tra: <strong>{target}</strong>.</p>}
    </div>
    <div className="ai-compatibility-products">{result.Products.map((product) => {
      const image = typeof product.ImageUrl === 'string' && /^(https?:\/\/|\/(?!\/))/i.test(product.ImageUrl) ? product.ImageUrl : null
      return <div className="ai-compatibility-product" key={`${product.ProductId}/${product.ProductVariantId ?? ''}`}>
        <small>{product.Kind === 'laptop' ? 'Laptop' : product.Kind === 'monitor' ? 'Màn hình' : 'Thiết bị'}</small>
        <Link to={productPath(product.Slug)} aria-label={`Xem chi tiết ${product.ProductName}`}>
          <StoreImage src={image} alt="" loading="lazy" onLoad={onLoad}
            fallback={<span className="ai-compatibility-image-fallback" aria-hidden="true">VT</span>} />
          <span><strong>{product.ProductName}</strong>{typeof product.VariantName === 'string' && <small>{product.VariantName}</small>}
            <span className="ai-compatibility-detail-link">Xem chi tiết</span></span>
        </Link>
        {product.InStock === false && <small>Hết hàng khi kiểm tra, kết quả giữ đúng phiên bản này.</small>}
        {strings(product.Facts).length > 0 ? <details><summary>Thông số cổng kết nối</summary><Lines items={product.Facts} /></details>
          : <p className="ai-compatibility-muted">Chưa rõ thông số cổng kết nối.</p>}
      </div>
    })}</div>
    <h5>KẾT QUẢ</h5>
    <div className="ai-compatibility-criteria">{result.Criteria.map((criterion) => <div key={criterion.Id}>
      <h6>{criterion.Label}</h6><Status status={criterion.Status} basis={result.Basis}
        modeBasis={MODE_CRITERIA.includes(criterion.Id) ? result.ModeBasis : undefined} requested={criterion.Requested !== false} />
      <p>{customerAiText(criterion.Summary)}</p>
      {strings(criterion.Evidence).length > 0 && <details><summary>Chi tiết cổng kết nối</summary><Lines items={criterion.Evidence} /></details>}
    </div>)}</div>
    {strings(result.Conditions).length > 0 && <><h5>Điều kiện và cách kết nối</h5><Lines items={result.Conditions} /></>}
    {strings(result.Missing).length > 0 && <div className="ai-compatibility-missing"><h5>Thông số còn thiếu cần kiểm tra</h5><Lines items={result.Missing} /></div>}
    <div className="ai-compatibility-explanation">
      <h5>GIẢI THÍCH KẾT QUẢ</h5><p>{customerAiText(result.Explanation)}</p>
      {result.AnalysisStatus === 'fallback' && <p role="status">Phần diễn giải AI tạm thời chưa hoàn tất. Bạn vẫn có thể xem kết quả kiểm tra và các điều kiện kết nối.</p>}
    </div>
    {strings(result.Limitations).length > 0 && <><h5>Giới hạn của kết luận</h5><Lines items={result.Limitations} /></>}
  </section>
}
