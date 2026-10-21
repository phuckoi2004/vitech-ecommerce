import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { buttonClassName } from '../../../components/shared/buttonStyles.js'
import useApiData from '../../../hooks/useApiData.js'
import { listCategoryOffers } from '../../../lib/catalog-api.js'
import { formatDiscountPercent, formatMoney } from '../../../lib/format.js'
import { categoryPath } from '../../routes/paths.js'
import { ArrowRightIcon } from '../icons.jsx'
import ScrollRail from './ScrollRail.jsx'

// Figma's promotional layout, with captions based on actual automatic discounts.
// Keep real category destinations when the design's sample categories do not exist.
function Shortcut({ category, offer, loading }) {
  let headline = 'Khám phá sản phẩm'
  if (loading) headline = <span className="home-shortcut-skeleton" aria-hidden="true" />
  else if (Number(offer?.MaxDiscountAmount) > 0) {
    if (/^(laptop|may-tinh-xach-tay)$/.test(category.Slug)) {
      const amount = Number(offer.MaxDiscountAmount)
      headline = `Ưu đãi đến ${amount >= 1_000_000
        ? `${(amount / 1_000_000).toLocaleString('vi-VN', { maximumFractionDigits: 6 })} TRIỆU`
        : formatMoney(amount)}`
    } else headline = `Giảm đến ${formatDiscountPercent(offer.MaxDiscountPercent)}`
  } else if (offer?.AvailableProductCount === 0) {
    headline = 'Sắp có hàng'
  }

  return <li className="home-shortcut">
    <h3>{category.Name}</h3>
    <p className="home-shortcut-headline">{headline}</p>
    <Link className={buttonClassName({ className: 'home-cta' })} to={categoryPath(category.Slug)}
      aria-label={`Mua ngay: ${category.Name}`}>
      Mua ngay <ArrowRightIcon className="size-4" />
    </Link>
  </li>
}

export default function CategoryShortcuts({ categories }) {
  const offers = useApiData('category-offers', (signal) => listCategoryOffers({ signal }))
  useEffect(() => {
    const timer = window.setInterval(offers.reload, 30_000)
    window.addEventListener('focus', offers.reload)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', offers.reload) }
  }, [offers.reload])

  if (categories.loading) {
    return <div className="home-shortcuts home-card" aria-hidden="true">
      <ul className="home-rail-track is-static">
        {Array.from({ length: 4 }, (_, index) => <li key={index} className="home-shortcut is-skeleton" />)}
      </ul>
    </div>
  }
  const items = categories.data ?? []
  if (!items.length) return null

  // Every root category gets a card; up to four fit across, the rest are a swipe (or an arrow) away.
  return <section className="home-shortcuts home-card" aria-label="Mua sắm theo danh mục" style={{ '--shortcut-count': items.length }}>
    <ScrollRail>{items.map((category) => <Shortcut key={category.CategoryId} category={category}
      offer={offers.data?.find((offer) => offer.CategoryId === category.CategoryId)} loading={offers.loading} />)}</ScrollRail>
  </section>
}
