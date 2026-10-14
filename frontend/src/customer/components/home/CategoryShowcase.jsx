import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import EmptyState from '../../../components/shared/EmptyState.jsx'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import useInView from '../../../hooks/useInView.js'
import { listCategories, listProductSummaries, loadProductCards, searchProducts } from '../../../lib/catalog-api.js'
import { categoryPath } from '../../routes/paths.js'
import { CategoryIcon, ChevronLeftIcon, ChevronRightIcon } from '../icons.jsx'
import ProductCard, { ProductCardSkeleton } from '../ProductCard.jsx'

const ROW_SIZE = 10

// Horizontally scrolling row of cards; on wide screens an arrow pages through it while there is more that way.
// The arrows are a pointer shortcut kept out of the tab order (each card is a link, and focusing it scrolls the
// row), so an arrow disappearing at the end never drops keyboard focus.
function ProductRail({ products }) {
  const track = useRef(null)
  const [edges, setEdges] = useState({ start: true, end: true })

  const measure = useCallback(() => {
    const element = track.current
    if (!element) return
    setEdges({ start: element.scrollLeft <= 4, end: element.scrollLeft + element.clientWidth >= element.scrollWidth - 4 })
  }, [])

  useEffect(() => {
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [measure, products])

  const page = (direction) => track.current?.scrollBy?.({ left: direction * track.current.clientWidth * 0.85, behavior: 'smooth' })

  return <div className="home-rail">
    {!edges.start && <button type="button" className="home-rail-nav is-prev" onClick={() => page(-1)} tabIndex={-1} aria-hidden="true"><ChevronLeftIcon /></button>}
    <ul className="home-rail-track" ref={track} onScroll={measure}>
      {products.map((product) => <li key={product.id}><ProductCard product={product} /></li>)}
    </ul>
    {!edges.end && <button type="button" className="home-rail-nav is-next" onClick={() => page(1)} tabIndex={-1} aria-hidden="true"><ChevronRightIcon /></button>}
  </div>
}

// Content of one tab: sub-category chips (child categories), brand chips and the newest products.
// Category and brand filters run on the server, including all active descendants.
function CategoryPanel({ category, brandPool, id, labelledBy }) {
  const [childId, setChildId] = useState('')
  const [brandId, setBrandId] = useState('')
  const children = useApiData(`children:${category.CategoryId}`, (signal) => listCategories({ parentId: category.CategoryId, signal }))
  const source = childId || category.CategoryId
  const brandProducts = useApiData(`brand-products:${source}`, (signal) => listProductSummaries({ categoryId: source, includeDescendants: true, signal }))
  const products = useApiData(`row:${source}:${brandId}`, async (signal) => {
    const page = await searchProducts({ categoryId: source, brandId: brandId || undefined, includeDescendants: true, pageSize: ROW_SIZE, signal })
    return loadProductCards(page.Items, { signal })
  })

  const cards = products.data ?? []
  const brandIds = new Set((brandProducts.data ?? []).map((item) => item.BrandId))
  const availableBrands = (brandPool.data ?? []).filter((brand) => brandIds.has(brand.BrandId))
  const shown = cards
  const childList = children.data ?? []
  const viewAll = childList.find((child) => child.CategoryId === childId) ?? category

  function pickChild(next) {
    setChildId(next === childId ? '' : next)
    setBrandId('')
  }

  let row
  if (products.loading) {
    row = <ul className="home-rail-track is-static" aria-hidden="true">
      {Array.from({ length: 5 }, (_, index) => <li key={index}><ProductCardSkeleton /></li>)}
    </ul>
  } else if (products.error) {
    row = <ErrorState title="Không tải được sản phẩm" message={products.error} onRetry={products.reload} className="py-8" />
  } else if (!shown.length) {
    row = <EmptyState headingLevel={3} title="Chưa có sản phẩm" description="Danh mục này đang được cập nhật sản phẩm." className="py-8" />
  } else {
    row = <ProductRail products={shown} />
  }

  return <div id={id} role={labelledBy ? 'tabpanel' : undefined} aria-labelledby={labelledBy} className="home-panel">
    {children.error && <div className="home-inline-error" role="alert">
      <span>Không tải được nhóm danh mục.</span><button type="button" onClick={children.reload}>Thử lại</button>
    </div>}
    {childList.length > 0 && <ul className="home-subcats" aria-label={`Nhóm ${category.Name}`}>
      {childList.map((child) => <li key={child.CategoryId}>
        <button type="button" className="home-subcat" aria-pressed={child.CategoryId === childId} onClick={() => pickChild(child.CategoryId)}>
          <CategoryIcon name={child.Name} /><span>{child.Name}</span>
        </button>
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
          <button type="button" className="home-brandchip" aria-pressed={brand.BrandId === brandId}
            onClick={() => setBrandId(brand.BrandId === brandId ? '' : brand.BrandId)}>{brand.Name}</button>
        </li>)}
      </ul>}
      <Link className="home-viewall" to={`${categoryPath(viewAll.Slug)}${brandId ? `?brand=${encodeURIComponent(brandId)}` : ''}`}>Xem tất cả<span aria-hidden="true"> ›</span><span className="sr-only"> {viewAll.Name}</span></Link>
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
