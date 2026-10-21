import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import categoryCircle from '../../../assets/storefront/category-circle.svg'
import useApiData from '../../../hooks/useApiData.js'
import { listProductSummaries } from '../../../lib/catalog-api.js'
import { PRICE_RANGES } from '../../../lib/catalog-filters.js'
import { categoryPath } from '../../routes/paths.js'
import { CategoryIcon, ChevronRightIcon } from '../icons.jsx'
import StoreImage from '../StoreImage.jsx'

const hoverEnabled = () => window.matchMedia?.('(hover: hover) and (pointer: fine)').matches ?? false

function MenuSection({ title, loading, error, onRetry, emptyText, children, hasItems }) {
  return <section className="home-megamenu-section" aria-label={title}>
    <h3>{title}</h3>
    {loading ? <div className="home-megamenu-loading" role="status">Đang tải…</div>
      : error ? <div className="home-megamenu-error" role="alert"><p>{error}</p><button type="button" onClick={onRetry}>Thử lại</button></div>
        : hasItems ? children : <p className="home-megamenu-empty">{emptyText}</p>}
  </section>
}

// Clicking a category opens its product list. Hovering it (mouse) or ArrowRight (keyboard) opens a panel whose brand
// and price links filter that list. A brand is never stored as a child category.
export default function CategoryMenu({ categories, brandPool }) {
  const [activeId, setActiveId] = useState(null)
  const root = useRef(null), panel = useRef(null), closeTimer = useRef(null), moveFocus = useRef(false)
  const id = useId()
  const active = categories.data?.find((category) => category.CategoryId === activeId)
  const products = useApiData(active ? `menu-brands:${active.CategoryId}` : null,
    (signal) => listProductSummaries({ categoryId: active.CategoryId, includeDescendants: true, signal }))
  const brandIds = new Set((products.data ?? []).map((product) => product.BrandId))
  const brands = (brandPool.data ?? []).filter((brand) => brandIds.has(brand.BrandId))

  useEffect(() => {
    if (!activeId) return
    function outside(event) { if (!root.current?.contains(event.target)) setActiveId(null) }
    document.addEventListener('pointerdown', outside)
    if (moveFocus.current) { panel.current?.querySelector('button')?.focus(); moveFocus.current = false }
    return () => document.removeEventListener('pointerdown', outside)
  }, [activeId])
  useEffect(() => () => clearTimeout(closeTimer.current), [])

  function close(restoreFocus = false) {
    clearTimeout(closeTimer.current)
    if (restoreFocus) root.current?.querySelector('[aria-expanded="true"]')?.focus()
    setActiveId(null)
  }
  function open(categoryId) { clearTimeout(closeTimer.current); setActiveId(categoryId) }
  function keyDown(event, categoryId) {
    if (event.key === 'Escape') { event.preventDefault(); close(true) }
    if (event.key === 'ArrowRight' && categoryId) {
      event.preventDefault()
      if (activeId === categoryId) (panel.current?.querySelector('a') ?? panel.current?.querySelector('button'))?.focus()
      else { moveFocus.current = true; open(categoryId) }
    }
  }

  let content
  if (categories.loading) content = <ul className="home-catmenu-list" aria-hidden="true">
    {Array.from({ length: 6 }, (_, index) => <li key={index}><span className="home-catmenu-item is-skeleton" /></li>)}
  </ul>
  else if (categories.error) content = <div className="home-catmenu-note" role="alert"><p>Không tải được danh mục.</p><button type="button" onClick={categories.reload}>Thử lại</button></div>
  else if (!categories.data?.length) content = <p className="home-catmenu-note">Chưa có danh mục sản phẩm.</p>
  else content = <ul className="home-catmenu-list">
    {categories.data.map((category) => <li key={category.CategoryId}>
      <Link to={categoryPath(category.Slug)} className={`home-catmenu-item${activeId === category.CategoryId ? ' is-active' : ''}`}
        aria-expanded={activeId === category.CategoryId} aria-controls={activeId === category.CategoryId ? id : undefined}
        onMouseEnter={() => { if (hoverEnabled()) open(category.CategoryId) }}
        onKeyDown={(event) => keyDown(event, category.CategoryId)}>
        <span className="home-catmenu-icon"><StoreImage src={category.ImageUrl} alt="" className="home-catmenu-photo" fallback={<><img src={categoryCircle} width="24" height="24" alt="" /><CategoryIcon name={category.Name} /></>} /></span>
        <span className="home-catmenu-label">{category.Name}</span><ChevronRightIcon className="home-catmenu-chevron" />
      </Link>
    </li>)}
  </ul>

  return <nav ref={root} className="home-catmenu" aria-label="Danh mục sản phẩm"
    onMouseEnter={() => clearTimeout(closeTimer.current)}
    onMouseLeave={() => { if (hoverEnabled() && !root.current?.contains(document.activeElement)) closeTimer.current = setTimeout(() => setActiveId(null), 160) }}
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) close() }}
    onKeyDown={(event) => { if (event.key === 'Escape') keyDown(event) }}>
    {content}
    {active && <div ref={panel} id={id} className="home-megamenu" role="region" aria-label={`Khám phá ${active.Name}`}>
      <header className="home-megamenu-heading"><h2>{active.Name}</h2>
        <button type="button" className="home-megamenu-close" aria-label="Đóng danh mục" onClick={() => close(true)}>×</button>
      </header>
      <MenuSection title="Thương hiệu" loading={products.loading || brandPool.loading} error={products.error || brandPool.error}
        onRetry={() => { products.reload(); if (brandPool.error) brandPool.reload() }} hasItems={brands.length > 0}
        emptyText="Chưa có thương hiệu có sản phẩm trong danh mục này.">
        <ul className="home-megamenu-brands">{brands.map((brand) => <li key={brand.BrandId}>
          <Link to={`${categoryPath(active.Slug)}?brand=${encodeURIComponent(brand.BrandId)}`} aria-label={brand.Name} title={brand.Name} onClick={() => close()}>
            <StoreImage src={brand.LogoUrl} alt="" loading="lazy" decoding="async" fallback={<span>{brand.Name}</span>} />
          </Link>
        </li>)}</ul>
      </MenuSection>
      <section className="home-megamenu-section home-megamenu-price" aria-label="Chọn theo giá">
        <h3>Chọn theo giá</h3>
        <ul>{PRICE_RANGES.map((range) => <li key={range.value}>
          <Link to={`${categoryPath(active.Slug)}?price=${range.value}`} onClick={() => close()}>{range.label}</Link>
        </li>)}</ul>
      </section>
    </div>}
  </nav>
}
