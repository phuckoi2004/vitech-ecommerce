import { useEffect, useId } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import EmptyState from '../../components/shared/EmptyState.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import {
  getCategoryBySlug, getCategoryFilters, listBanners, listCategories, listNews, loadProductCards, searchProducts,
} from '../../lib/catalog-api.js'
import { LISTING_SORTS, findPriceRange, hasListingFilters, knownSpecs, newsAbout, readListing } from '../../lib/catalog-filters.js'
import BannerLink from '../components/BannerLink.jsx'
import CategoryCriteria from '../components/category/CategoryCriteria.jsx'
import ProductCard, { ProductCardSkeleton } from '../components/ProductCard.jsx'
import StoreImage from '../components/StoreImage.jsx'
import useProductPages from '../hooks/useProductPages.js'
import { HOME_PATH, categoryPath, newsPath } from '../routes/paths.js'
import './CategoryPage.css'

const PAGE_SIZE = 20
const NEWS_COUNT = 4
const lower = (text) => text.toLocaleLowerCase('vi-VN')

function Card({ title, headingLevel = 2, className = '', children }) {
  const id = useId()
  const Heading = `h${headingLevel}`
  return <section className={`catalog-card ${className}`} aria-labelledby={id}>
    <Heading id={id}>{title}</Heading>
    {children}
  </section>
}

// Figma "Advertising Banner": two banners for this category, at their own proportions. The server picks them by
// where they link: this category, its sub-categories and products, a parent category, then general promotions.
function Banners({ categoryId }) {
  const banners = useApiData(`banners:${categoryId}`, (signal) => listBanners({ categoryId, signal }))
  const shown = (banners.data ?? []).slice(0, 2)
  if (!shown.length) return null
  return <section className="catalog-banners" aria-label="Chương trình khuyến mãi">
    {shown.map((banner) => <BannerLink key={banner.BannerId} banner={banner} className="catalog-banner">
      <StoreImage src={banner.ImageUrl} alt={banner.Title} loading="lazy" />
    </BannerLink>)}
  </section>
}

// Figma "Phone News": recent articles that mention the category, hidden when none do.
function News({ category, root }) {
  const news = useApiData('catalog-news', (signal) => listNews({ pageSize: 50, signal }))
  const articles = newsAbout(news.data?.Items ?? [], [category.Name, root.Name]).slice(0, NEWS_COUNT)
  if (!articles.length) return null
  return <Card title={`Tin tức ${lower(category.Name)}`} className="catalog-news">
    <ul>{articles.map((article) => <li key={article.NewsArticleId}>
      <Link to={newsPath(article.Slug)}>
        <StoreImage src={article.ThumbnailUrl} alt="" loading="lazy" fallback={<span className="catalog-news-image" aria-hidden="true" />} />
        <h3>{article.Title}</h3>
        {article.Summary && <p>{article.Summary}</p>}
        <span className="catalog-news-more" aria-hidden="true">Xem thêm ›</span>
      </Link>
    </li>)}</ul>
  </Card>
}

function Results({ category, listing, priceRange, specs, waiting, onClear }) {
  const key = waiting ? null : JSON.stringify([category.CategoryId, listing.brandId, priceRange?.value ?? '', listing.sort,
    listing.inStock, listing.newArrivals, specs])
  const results = useProductPages(key, async (page, signal) => {
    const response = await searchProducts({ categoryId: category.CategoryId, includeDescendants: true, brandId: listing.brandId || undefined,
      minPrice: priceRange?.minPrice, maxPrice: priceRange?.maxPrice, sort: listing.sort, inStock: listing.inStock,
      newArrivals: listing.newArrivals, specs, page, pageSize: PAGE_SIZE, signal })
    return { ...response, cards: await loadProductCards(response.Items, { signal }) }
  })
  const remaining = results.remaining
  const firstLoad = results.loading && !results.products.length

  return <>
    <Card title={`${category.Name} nổi bật`} className="catalog-results">
      <p className="sr-only" role="status">{firstLoad ? 'Đang tải sản phẩm…' : `${results.total} sản phẩm`}</p>
      {results.products.length > 0 || firstLoad ? <ul className="catalog-products">
        {results.products.map((product) => <li key={product.id}><ProductCard product={product} /></li>)}
        {results.loading && Array.from({ length: firstLoad ? 10 : 5 }, (_, index) => <li key={`loading-${index}`}><ProductCardSkeleton /></li>)}
      </ul> : !results.error && <EmptyState title="Không có sản phẩm phù hợp" description="Hãy thử bỏ bớt tiêu chí hoặc chọn mức giá khác."
        headingLevel={3} action={hasListingFilters(listing) && <button type="button" className="catalog-clear" onClick={onClear}>Xóa bộ lọc</button>} />}
      {results.error && <ErrorState message={results.error} onRetry={results.retry} />}
    </Card>
    {remaining > 0 && !results.error && <button type="button" className="catalog-more" onClick={results.more} disabled={results.loading}>
      {results.loading ? 'Đang tải…' : <>Xem thêm {remaining} sản phẩm <span aria-hidden="true">↓</span></>}
    </button>}
  </>
}

function Listing({ category, categories }) {
  const [params, setParams] = useSearchParams()
  const listing = readListing(params)
  const filters = useApiData(`category-filters:${category.CategoryId}`, (signal) => getCategoryFilters(category.CategoryId, { signal }))
  const all = categories.data ?? []
  const parent = all.find((item) => item.CategoryId === category.ParentCategoryId)
  const root = parent ?? category
  const byOrder = (a, b) => a.DisplayOrder - b.DisplayOrder || a.Name.localeCompare(b.Name, 'vi')
  const children = all.filter((item) => item.ParentCategoryId === category.CategoryId)
  const needs = (children.length ? children : all.filter((item) => parent && item.ParentCategoryId === parent.CategoryId)).toSorted(byOrder)
  const group = children.length ? category : parent
  const priceRange = findPriceRange(listing.price, filters.data?.PriceRanges)
  // A range from the homepage menu stays visible (and removable) even when the category's own ranges differ.
  const ownRanges = filters.data?.PriceRanges ?? []
  const priceOptions = priceRange && !ownRanges.some((range) => range.Value === priceRange.value)
    ? [{ Value: priceRange.value, Label: priceRange.label }, ...ownRanges] : ownRanges
  // Chosen criteria wait for the category's filters, so an option it no longer offers is dropped, not an error.
  const specs = filters.data ? knownSpecs(listing.specs, filters.data.Facets) : []
  const waiting = listing.specs.length > 0 && filters.loading

  useEffect(() => { document.title = `${category.Name} | VieTech` }, [category.Name])

  function change(values) {
    const next = { ...listing, ...values }
    const query = new URLSearchParams()
    if (next.brandId) query.set('brand', next.brandId)
    if (next.price) query.set('price', next.price)
    if (next.sort !== LISTING_SORTS[0].value) query.set('sort', next.sort)
    if (next.inStock) query.set('stock', '1')
    if (next.newArrivals) query.set('new', '1')
    for (const spec of next.specs) query.append('spec', spec)
    setParams(query)
  }
  const clear = () => change({ brandId: '', price: '', inStock: false, newArrivals: false, specs: [] })

  return <div className="catalog-page">
    <nav className="catalog-breadcrumb" aria-label="Đường dẫn danh mục"><ol>
      <li><Link to={HOME_PATH}>Trang chủ</Link></li>
      {parent && <li><Link to={categoryPath(parent.Slug)}>{parent.Name}</Link></li>}
      <li aria-current="page">{category.Name}</li>
    </ol></nav>
    <Banners categoryId={category.CategoryId} />

    <section className="catalog-card" aria-labelledby="catalog-title">
      <h1 id="catalog-title">{category.Name}</h1>
      {filters.data?.Brands.length > 0 && <>
        <h2 className="catalog-subtitle">Chọn thương hiệu</h2>
        <ul className="catalog-brands">{filters.data.Brands.map((brand) => <li key={brand.BrandId}>
          <button type="button" className="catalog-tile" aria-pressed={listing.brandId === brand.BrandId}
            onClick={() => change({ brandId: listing.brandId === brand.BrandId ? '' : brand.BrandId })}>{brand.Name}</button>
        </li>)}</ul>
      </>}
      {filters.error && <ErrorState message={filters.error} onRetry={filters.reload} />}
    </section>

    {needs.length > 0 && <Card title="Chọn theo nhu cầu">
      <nav aria-label={`Nhóm ${lower(group.Name)}`}><ul className="catalog-needs">{needs.map((item) => <li key={item.CategoryId}>
        <Link className="catalog-tile" to={categoryPath(item.Slug)}
          aria-current={item.CategoryId === category.CategoryId ? 'page' : undefined}>{item.Name}</Link>
      </li>)}</ul></nav>
    </Card>}

    <CategoryCriteria listing={listing} priceRanges={priceOptions} facets={filters.data?.Facets ?? []}
      needs={needs} currentCategoryId={category.CategoryId} onChange={change} onClear={clear} active={hasListingFilters(listing)} />

    <Card title="Sắp xếp theo">
      <div className="catalog-sorts" role="group" aria-label="Sắp xếp sản phẩm">
        {LISTING_SORTS.map((sort) => <button key={sort.value} type="button" className="catalog-sort" aria-pressed={listing.sort === sort.value}
          onClick={() => change({ sort: sort.value })}>{sort.label}</button>)}
      </div>
    </Card>

    <Results category={category} listing={listing} priceRange={priceRange} specs={specs} waiting={waiting} onClear={clear} />

    {category.Description?.trim() && <Card title={`Thông tin về ${lower(category.Name)}`} className="catalog-intro">
      {category.Description.trim().split(/\n\s*\n|\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}
    </Card>}
    <News category={category} root={root} />
  </div>
}

// Customer category page (Figma "Danh sách sản phẩm", docs/customer-category-listing.md). A child category uses its
// root's criteria and lists its own products; a root category also lists its children's products.
export default function CategoryPage() {
  const { slug } = useParams()
  const category = useApiData(`category:${slug}`, (signal) => getCategoryBySlug(slug, { signal }))
  const categories = useApiData('catalog-category-navigation', (signal) => listCategories({ signal }))
  if (category.loading) return <LoadingState />
  if (category.error) return <ErrorState message={category.error} onRetry={category.reload} />
  return <Listing key={category.data.CategoryId} category={category.data} categories={categories} />
}
