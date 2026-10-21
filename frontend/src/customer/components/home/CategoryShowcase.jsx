import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import EmptyState from '../../../components/shared/EmptyState.jsx'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import useInView from '../../../hooks/useInView.js'
import { listCategories, listProductSummaries, loadProductCards, searchProducts } from '../../../lib/catalog-api.js'
import { categoryPath } from '../../routes/paths.js'
import { CategoryIcon } from '../icons.jsx'
import ProductCard, { ProductCardSkeleton } from '../ProductCard.jsx'
import StoreImage from '../StoreImage.jsx'
import ScrollRail from './ScrollRail.jsx'

const ROW_SIZE = 10

function ProductRail({ products }) {
  return <ScrollRail>{products.map((product) => <li key={product.id}><ProductCard product={product} /></li>)}</ScrollRail>
}

// Content of one tab: sub-category and brand links, and the newest products of the category (with its children).
// As on CellphoneS, a sub-category or brand opens its product list page right away instead of filtering this row.
function CategoryPanel({ category, brandPool, id, labelledBy }) {
  const children = useApiData(`children:${category.CategoryId}`, (signal) => listCategories({ parentId: category.CategoryId, signal }))
  const brandProducts = useApiData(`brand-products:${category.CategoryId}`, (signal) => listProductSummaries({ categoryId: category.CategoryId, includeDescendants: true, signal }))
  const products = useApiData(`row:${category.CategoryId}`, async (signal) => {
    const page = await searchProducts({ categoryId: category.CategoryId, includeDescendants: true, pageSize: ROW_SIZE, signal })
    return loadProductCards(page.Items, { signal })
  })

  const cards = products.data ?? []
  const brandIds = new Set((brandProducts.data ?? []).map((item) => item.BrandId))
  const availableBrands = (brandPool.data ?? []).filter((brand) => brandIds.has(brand.BrandId))
  const childList = children.data ?? []

  let row
  if (products.loading) {
    row = <ul className="home-rail-track is-static" aria-hidden="true">
      {Array.from({ length: 5 }, (_, index) => <li key={index}><ProductCardSkeleton /></li>)}
    </ul>
  } else if (products.error) {
    row = <ErrorState title="Không tải được sản phẩm" message={products.error} onRetry={products.reload} className="py-8" />
  } else if (!cards.length) {
    row = <EmptyState headingLevel={3} title="Chưa có sản phẩm" description="Danh mục này đang được cập nhật sản phẩm." className="py-8" />
  } else {
    row = <ProductRail products={cards} />
  }

  return <div id={id} role={labelledBy ? 'tabpanel' : undefined} aria-labelledby={labelledBy} className="home-panel">
    {children.error && <div className="home-inline-error" role="alert">
      <span>Không tải được nhóm danh mục.</span><button type="button" onClick={children.reload}>Thử lại</button>
    </div>}
    {childList.length > 0 && <ul className="home-subcats" aria-label={`Nhóm ${category.Name}`}>
      {childList.map((child) => <li key={child.CategoryId}>
        <Link className="home-subcat" to={categoryPath(child.Slug)}>
          <StoreImage src={child.ImageUrl} alt="" loading="lazy" fallback={<CategoryIcon name={child.Name} />} /><span>{child.Name}</span>
        </Link>
      </li>)}
    </ul>}
    <div className="home-brandbar">
      {(brandProducts.error || brandPool.error) && <div className="home-inline-error" role="alert">
        <span>Không tải được bộ lọc thương hiệu.</span><button type="button" onClick={() => {
          if (brandProducts.error) brandProducts.reload()
          if (brandPool.error) brandPool.reload()
        }}>Thử lại</button>
      </div>}
      {availableBrands.length > 0 && <ul className="home-brandchips" aria-label="Lọc theo thương hiệu">
        {availableBrands.map((brand) => <li key={brand.BrandId}>
          <Link className="home-brandchip" to={`${categoryPath(category.Slug)}?brand=${encodeURIComponent(brand.BrandId)}`}>{brand.Name}</Link>
        </li>)}
      </ul>}
      <Link className="home-viewall" to={categoryPath(category.Slug)}>Xem tất cả<span aria-hidden="true"> ›</span><span className="sr-only"> {category.Name}</span></Link>
    </div>
    {row}
  </div>
}

// Figma "Điện thoại/Laptop" and "Máy tính/Linh kiện": one or two root categories as tabs. Loads when the
// visitor scrolls near it.
export default function CategoryShowcase({ categories, brandPool }) {
  const [ref, seen] = useInView()
  const [activeId, setActiveId] = useState(categories[0].CategoryId)
  const baseId = useId()
  const active = categories.find((category) => category.CategoryId === activeId) ?? categories[0]
  const tabbed = categories.length > 1
  const panelId = `${baseId}-panel`

  function onTabKey(event, position) {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const next = categories[(position + step + categories.length) % categories.length]
    setActiveId(next.CategoryId)
    document.getElementById(`${baseId}-tab-${next.CategoryId}`)?.focus()
  }

  return <section ref={ref} className="home-showcase home-card" aria-label={categories.map((category) => category.Name).join(', ')}>
    {tabbed
      ? <div className="home-tabs" role="tablist">
        {categories.map((category, position) => {
          const selected = category.CategoryId === active.CategoryId
          return <button key={category.CategoryId} id={`${baseId}-tab-${category.CategoryId}`} type="button" role="tab"
            className="home-tab" aria-selected={selected} aria-controls={panelId} tabIndex={selected ? 0 : -1}
            onClick={() => setActiveId(category.CategoryId)} onKeyDown={(event) => onTabKey(event, position)}>
            {category.Name}
          </button>
        })}
      </div>
      : <h2 className="home-tabs"><span className="home-tab is-active">{active.Name}</span></h2>}
    {seen
      ? <CategoryPanel key={active.CategoryId} category={active} brandPool={brandPool} id={panelId}
        labelledBy={tabbed ? `${baseId}-tab-${active.CategoryId}` : undefined} />
      : <div className="home-panel is-waiting" />}
  </section>
}
