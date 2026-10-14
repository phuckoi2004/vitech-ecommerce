import { Link } from 'react-router-dom'
import Money from '../../components/shared/Money.jsx'
import { formatCompactCount, formatRating } from '../../lib/format.js'
import { productPath } from '../routes/paths.js'
import StoreImage from './StoreImage.jsx'
import './ProductCard.css'

// Product card from toProductCard() (lib/catalog-api.js): image, name, lowest variant price, rating, sold count.
// There is no crossed-out price or discount badge: catalog prices carry no discount, coupons apply at checkout.
export default function ProductCard({ product, headingLevel = 3 }) {
  const Heading = `h${headingLevel}`
  const rated = product.reviewCount > 0

  return <article className="pcard">
    <Link className="pcard-link" to={productPath(product.slug)}>
      <div className="pcard-media">
        <StoreImage src={product.imageUrl} alt="" loading="lazy" decoding="async"
          fallback={<span className="pcard-noimage" aria-hidden="true">VieTech</span>} />
        {!product.inStock && <span className="pcard-badge">Hết hàng</span>}
      </div>
      <Heading className="pcard-name">{product.name}</Heading>
      <p className="pcard-price">
        {product.price === null
          ? <span className="pcard-noprice">Đang cập nhật giá</span>
          : <>{product.priceFrom && <span className="pcard-from">Từ </span>}<Money value={product.price} /></>}
      </p>
      <p className="pcard-meta">
        {rated && <span><span className="sr-only">Đánh giá </span><span aria-hidden="true">★ </span>{formatRating(product.rating)}</span>}
        {rated && product.sold > 0 && <span aria-hidden="true"> • </span>}
        {product.sold > 0 && <span>Đã bán {formatCompactCount(product.sold)}</span>}
      </p>
    </Link>
  </article>
}

// Same footprint as a card while the list loads.
export function ProductCardSkeleton() {
  return <div className="pcard is-skeleton" aria-hidden="true">
    <div className="pcard-media" />
    <span className="pcard-line" />
    <span className="pcard-line is-short" />
  </div>
}
