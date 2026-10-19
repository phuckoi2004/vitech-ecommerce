import { useParams, useSearchParams } from 'react-router-dom'
import EmptyState from '../../components/shared/EmptyState.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import Pagination from '../../components/shared/Pagination.jsx'
import useApiData from '../../hooks/useApiData.js'
import { getBrandBySlug, getCategoryBySlug, listBrands, loadProductCards, searchProducts } from '../../lib/catalog-api.js'
import { PRICE_RANGES } from '../../lib/catalog-filters.js'
import ProductCard from '../components/ProductCard.jsx'
import CategoryNavigation from '../components/CategoryNavigation.jsx'
import './ShoppingPages.css'

const PAGE_SIZE = 20

function Results({ title, category, categoryId, fixedBrandId }) {
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1)
  const keyword = params.get('q') ?? ''
  const brandId = fixedBrandId || params.get('brand') || ''
  const priceRange = PRICE_RANGES.find((range) => range.value === params.get('price'))
  const brands = useApiData('catalog-brands', (signal) => listBrands({ signal }))
  const products = useApiData(`catalog:${categoryId ?? ''}:${brandId}:${keyword}:${priceRange?.value ?? ''}:${page}`, async (signal) => {
    const response = await searchProducts({ categoryId, brandId: brandId || undefined, keyword,
      includeDescendants: !!categoryId, minPrice: priceRange?.minPrice, maxPrice: priceRange?.maxPrice, page, pageSize: PAGE_SIZE, signal })
    return { ...response, cards: await loadProductCards(response.Items, { signal }) }
  })

  function change(name, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(name, String(value)); else next.delete(name)
    if (name !== 'page') next.delete('page')
    setParams(next)
  }

  return <div className="shopping-page">
    <h1>{title || (keyword ? `Kết quả tìm kiếm: ${keyword}` : 'Sản phẩm')}</h1>
    {category && <CategoryNavigation category={category} />}
    {category?.ParentCategoryId && category.Description && <p className="catalog-category-description">{category.Description}</p>}
    <div className="shopping-catalog-filters">
      {!fixedBrandId && brands.data?.length > 0 && <label className="shopping-filter">Thương hiệu
        <select value={brandId} onChange={(event) => change('brand', event.target.value)}>
          <option value="">Tất cả thương hiệu</option>
          {brands.data.map((brand) => <option key={brand.BrandId} value={brand.BrandId}>{brand.Name}</option>)}
        </select>
      </label>}
      <label className="shopping-filter">Khoảng giá
        <select value={priceRange?.value ?? ''} onChange={(event) => change('price', event.target.value)}>
          <option value="">Tất cả mức giá</option>
          {PRICE_RANGES.map((range) => <option key={range.value} value={range.value}>{range.label}</option>)}
        </select>
      </label>
    </div>
    {products.loading ? <LoadingState label="Đang tải sản phẩm…" />
      : products.error ? <ErrorState message={products.error} onRetry={products.reload} />
        : <>
          <p className="shopping-muted">{products.data.Total} sản phẩm</p>
          {products.data.cards.length ? <ul className="shopping-products">
            {products.data.cards.map((product) => <li key={product.id}><ProductCard product={product} /></li>)}
          </ul> : <EmptyState title="Không có sản phẩm phù hợp" description="Hãy thử từ khóa hoặc bộ lọc khác." />}
          <Pagination page={page} pageSize={PAGE_SIZE} total={products.data.Total} onPageChange={(next) => change('page', next)} />
        </>}
  </div>
}

export default function CatalogPage({ kind = 'search' }) {
  const { slug } = useParams()
  const scope = useApiData(kind === 'search' ? null : `${kind}:${slug}`, (signal) =>
    kind === 'category' ? getCategoryBySlug(slug, { signal }) : getBrandBySlug(slug, { signal }))
  if (kind !== 'search') {
    if (scope.loading) return <LoadingState />
    if (scope.error) return <ErrorState message={scope.error} onRetry={scope.reload} />
  }
  return <Results title={scope.data?.Name} category={kind === 'category' ? scope.data : undefined}
    categoryId={kind === 'category' ? scope.data.CategoryId : undefined}
    fixedBrandId={kind === 'brand' ? scope.data.BrandId : undefined} />
}
