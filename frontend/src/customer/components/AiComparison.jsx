import { useId } from 'react'
import { Link } from 'react-router-dom'
import Money from '../../components/shared/Money.jsx'
import { productPath } from '../routes/paths.js'
import StoreImage from './StoreImage.jsx'
import { comparisonCaveats, comparisonDifferences, comparisonRows, comparisonValueLines, isComparison } from './ai-comparison.js'
import { customerAiText } from './ai-customer-wording.js'

const missing = 'Chưa rõ'
const strings = (value) => Array.isArray(value) ? value.filter((item) => typeof item === 'string').map(customerAiText) : []


export default function AiComparison({ comparison, onLoad }) {
  const titleId = useId()
  if (!isComparison(comparison)) return null
  const products = comparison.Products
  const needs = strings(comparison.Needs)
  const caveats = comparisonCaveats(comparison.Caveats).map(customerAiText)
  const recommendation = customerAiText(comparison.Recommendation)
  const rows = comparisonRows(comparison)
  const differences = strings(comparisonDifferences(comparison.Differences))
  return <section className="ai-comparison" aria-labelledby={titleId}>
    <h4 id={titleId}>So sánh sản phẩm</h4>
    <p className={`ai-comparison-hint${products.length === 2 ? ' is-two-columns' : ''}`}>Vuốt hoặc cuộn ngang để xem đủ {products.length} sản phẩm.</p>
    <div className="ai-comparison-scroll" role="region" aria-label="Bảng so sánh sản phẩm, có thể cuộn ngang" tabIndex={0}>
      <table className="ai-comparison-table" style={{ '--ai-comparison-columns': products.length }}>
        <caption className="sr-only">Thông số và giá của các phiên bản được chọn</caption>
        <thead><tr><th scope="col">Đặc điểm</th>{products.map((product) => {
          const src = typeof product.ImageUrl === 'string' && /^(https?:\/\/|\/(?!\/))/i.test(product.ImageUrl) ? product.ImageUrl : null
          return <th scope="col" key={product.ProductVariantId}>
            <StoreImage src={src} alt="" loading="lazy" onLoad={onLoad} fallback={<span className="ai-comparison-image-fallback" aria-hidden="true">VT</span>} />
            <strong>{product.ProductName}</strong><small>{product.VariantName}</small>
            <Link to={productPath(product.Slug)} aria-label={`Xem chi tiết ${product.ProductName}`}>Xem chi tiết</Link>
          </th>
        })}</tr></thead>
        <tbody>
          <tr><th scope="row">Thương hiệu</th>{products.map((p) => <td key={p.ProductVariantId}>{p.Brand || missing}</td>)}</tr>
          <tr><th scope="row">Danh mục</th>{products.map((p) => <td key={p.ProductVariantId}>{p.Category || missing}</td>)}</tr>
          <tr><th scope="row">Giá bán</th>{products.map((p) => <td key={p.ProductVariantId}><Money className="ai-chat-price" value={p.Price} /></td>)}</tr>
          <tr><th scope="row">Tình trạng</th>{products.map((p) => <td key={p.ProductVariantId}>{p.InStock ? 'Còn hàng' : 'Hết hàng'}</td>)}</tr>
          {rows.map((row, index) => <tr key={`${row.Key}-${index}`}><th scope="row">{row.Label}</th>
            {row.Values.map((value, column) => {
              const text = customerAiText(value || missing)
              return <td key={products[column].ProductVariantId} className={text === missing ? 'is-missing' : undefined}>
                <span className="ai-comparison-spec-lines">{comparisonValueLines(row.Key, value || missing).map((line, i) =>
                  <span key={i}>{customerAiText(line)}</span>)}</span>
              </td>
            })}
          </tr>)}
        </tbody>
      </table>
    </div>
    <div className="ai-comparison-analysis">
      <h4>Nhận xét</h4>
      {needs.length > 0 && <p>Nhu cầu: {needs.join(', ')}.</p>}
      {products.map((product) => <section className="ai-comparison-verdict" key={product.ProductVariantId} aria-label={`Nhận xét ${product.ProductName}`}>
        <h5>{product.ProductName}</h5>
        <p className="ai-comparison-variant">{product.VariantName}</p>
        {needs.length > 0 && typeof product.Score === 'number' && <p>Mức phù hợp với nhu cầu: {Math.round(product.Score * 100)}%.</p>}
        {strings(product.Strengths).length > 0 && <><p><strong>Điểm mạnh</strong></p>
          <ul>{strings(product.Strengths).map((line, i) => <li className="ai-comparison-multiline" key={i}>{line}</li>)}</ul></>}
        {strings(product.Limitations).length > 0 && <><p><strong>Điểm cần cân nhắc</strong></p>
          <ul>{strings(product.Limitations).map((line, i) => <li key={i}>{line}</li>)}</ul></>}
      </section>)}
      {differences.length > 0 && <><h5>Khác biệt quan trọng</h5>
        <ul>{differences.map((line, i) => <li className="ai-comparison-multiline" key={i}>{line}</li>)}</ul></>}
      {recommendation && <><h5>Gợi ý theo nhu cầu</h5><p className="ai-comparison-multiline">{recommendation}</p></>}
      {comparison.AnalysisStatus === 'fallback' && <p role="status">Nhận xét tạm thời chưa hoàn tất. Bạn vẫn có thể xem bảng so sánh.</p>}
      {caveats.length > 0 && <><h5>Về yêu cầu của bạn</h5>
        <ul>{caveats.map((line, i) => <li key={i}>{line}</li>)}</ul></>}
    </div>
  </section>
}
