import { Link } from 'react-router-dom'
import { buttonClassName } from '../../../components/shared/buttonStyles.js'
import useApiData from '../../../hooks/useApiData.js'
import { searchProducts } from '../../../lib/catalog-api.js'
import { categoryPath } from '../../routes/paths.js'
import { ArrowRightIcon } from '../icons.jsx'

// One card of Figma "Category Promos". The design's "Giảm đến 30%" lines have no data behind them (catalog
// prices carry no discount), so the card shows how many products the category has on sale.
function Shortcut({ category }) {
  const count = useApiData(`count:${category.CategoryId}`,
    (signal) => searchProducts({ categoryId: category.CategoryId, includeDescendants: true, pageSize: 1, signal }).then((page) => page.Total))

  let headline = <span className="home-shortcut-skeleton" aria-hidden="true" />
  if (!count.loading) {
    if (count.error) headline = 'Xem sản phẩm'
    else headline = count.data ? `${count.data.toLocaleString('vi-VN')} sản phẩm` : 'Sắp có hàng'
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
  if (categories.loading) {
    return <div className="home-shortcuts home-card" aria-hidden="true">
      <ul>{Array.from({ length: 4 }, (_, index) => <li key={index} className="home-shortcut is-skeleton" />)}</ul>
    </div>
  }
  const items = (categories.data ?? []).slice(0, 4)
  if (!items.length) return null

  return <section className="home-shortcuts home-card" aria-label="Mua sắm theo danh mục"
    style={{ '--shortcut-columns': items.length, '--shortcut-small-columns': Math.min(items.length, 2) }}>
    <ul>{items.map((category) => <Shortcut key={category.CategoryId} category={category} />)}</ul>
  </section>
}
