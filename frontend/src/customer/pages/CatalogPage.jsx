import { useEffect, useId } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import EmptyState from '../../components/shared/EmptyState.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import { getBrandBySlug, getSearchFilters, listNews, loadProductCards, searchProducts } from '../../lib/catalog-api.js'
import { hasAllWords } from '../../lib/search-text.js'
import ProductCard, { ProductCardSkeleton } from '../components/ProductCard.jsx'
import StoreImage from '../components/StoreImage.jsx'
import useProductPages from '../hooks/useProductPages.js'
import { HOME_PATH, NEWS_PATH, SEARCH_PATH, newsPath } from '../routes/paths.js'
import './ShoppingPages.css'
import './CatalogPage.css'

const PAGE_SIZE = 20
const ARTICLE_COUNT = 6

// "Bài viết liên quan": recent articles whose title or summary has every word of the search.
function RelatedArticles({ keyword }) {
  const id = useId()
  const news = useApiData(keyword ? 'search-news' : null, (signal) => listNews({ pageSize: 50, signal }))
  const articles = (news.data?.Items ?? []).filter((article) => hasAllWords(`${article.Title} ${article.Summary ?? ''}`, keyword))
    .slice(0, ARTICLE_COUNT)
  if (!articles.length) return null
  return <aside className="search-articles" aria-labelledby={id}>
    <h2 id={id}>Bài viết liên quan</h2>
    <ul>{articles.map((article) => <li key={article.NewsArticleId}>
      <Link to={newsPath(article.Slug)}>
        <StoreImage src={article.ThumbnailUrl} alt="" loading="lazy" fallback={<span className="search-article-image" aria-hidden="true" />} />
        <span>{article.Title}</span>
      </Link>
    </li>)}</ul>
    <Link className="search-articles-all" to={NEWS_PATH}>Xem tất cả bài viết <span aria-hidden="true">›</span></Link>
  </aside>
}

// Search results and brand pages, laid out like CellphoneS: what was found, category chips from the results, a short
// sort row and "Xem thêm" instead of page numbers. Category pages have their own layout (CategoryPage).
function Results({ title, fixedBrandId }) {
  const [params, setParams] = useSearchParams()
  const keyword = (params.get('q') ?? '').trim()
  const categoryId = params.get('category') || ''
  const defaultSort = keyword ? 'relevance' : 'newest'
  const sorts = [{ value: defaultSort, label: keyword ? 'Liên quan' : 'Mới nhất' },
    { value: 'price_desc', label: 'Giá cao' }, { value: 'price_asc', label: 'Giá thấp' }]
  const sort = sorts.find((item) => item.value === params.get('sort'))?.value ?? defaultSort
  const heading = title || (keyword ? `Kết quả tìm kiếm cho: '${keyword}'` : 'Tất cả sản phẩm')
  const choices = useApiData(JSON.stringify(['search-filters', fixedBrandId, keyword]),
    (signal) => getSearchFilters({ keyword, brandId: fixedBrandId, signal }))
  const categories = choices.data?.Categories ?? []
  const results = useProductPages(JSON.stringify(['search', fixedBrandId, categoryId, keyword, sort]), async (page, signal) => {
    const response = await searchProducts({ keyword, brandId: fixedBrandId, categoryId: categoryId || undefined,
      includeDescendants: !!categoryId, sort: sort === defaultSort ? undefined : sort, page, pageSize: PAGE_SIZE, signal })
    return { ...response, cards: await loadProductCards(response.Items, { signal }) }
  })
  const firstLoad = results.loading && !results.products.length

  useEffect(() => { document.title = `${heading} | VieTech` }, [heading])

  function change(name, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(name, value); else next.delete(name)
    next.delete('page')
    setParams(next)
  }

  return <div className="shopping-page customer-catalog">
    <nav className="search-breadcrumb" aria-label="Đường dẫn trang sản phẩm"><ol>
      <li><Link to={HOME_PATH}>Trang chủ</Link></li>
      <li aria-current="page">{heading}</li>
    </ol></nav>
    <h1 className={title ? 'search-title' : 'sr-only'}>{heading}</h1>
    <p className="search-summary" role="status">{firstLoad ? 'Đang tìm sản phẩm…' : results.error && !results.products.length
      ? 'Chưa tải được kết quả' : <>Tìm thấy <strong>{results.total}</strong> sản phẩm{keyword && <> cho từ khoá <strong>'{keyword}'</strong></>}</>}</p>

    {(categories.length > 1 || categoryId) && <div className="search-chips" role="group" aria-label="Danh mục">
      <button type="button" aria-pressed={!categoryId} onClick={() => change('category', '')}>Tất cả</button>
      {categories.map((category) => <button key={category.CategoryId} type="button" aria-pressed={category.CategoryId === categoryId}
        onClick={() => change('category', category.CategoryId === categoryId ? '' : category.CategoryId)}>{category.Name}</button>)}
    </div>}
    <section className="search-sort" aria-labelledby="search-sort-title">
      <h2 id="search-sort-title">Sắp xếp theo</h2>
      <div className="search-chips">{sorts.map((item) => <button key={item.value} type="button" aria-pressed={item.value === sort}
        onClick={() => change('sort', item.value === defaultSort ? '' : item.value)}>{item.label}</button>)}</div>
    </section>

    <div className="search-layout">
      <section className="search-results" aria-label="Kết quả sản phẩm" aria-busy={results.loading}>
        {results.products.length > 0 || firstLoad ? <ul className="shopping-products">
          {results.products.map((product) => <li key={product.id}><ProductCard product={product} /></li>)}
          {results.loading && Array.from({ length: firstLoad ? 10 : 5 }, (_, index) => <li key={`loading-${index}`}><ProductCardSkeleton /></li>)}
        </ul> : !results.error && <EmptyState title="Không có sản phẩm phù hợp" description="Hãy thử từ khóa ngắn hơn hoặc chọn danh mục khác."
          action={<Link className="search-all-products" to={SEARCH_PATH}>Xem tất cả sản phẩm</Link>} />}
        {results.error && <ErrorState message={results.error} onRetry={results.retry} />}
        {results.remaining > 0 && !results.error && <button type="button" className="search-more" onClick={results.more} disabled={results.loading}>
          {results.loading ? 'Đang tải…' : <>Xem thêm {results.remaining} sản phẩm <span aria-hidden="true">↓</span></>}
        </button>}
      </section>
      <RelatedArticles keyword={keyword} />
    </div>
  </div>
}

export default function CatalogPage({ kind = 'search' }) {
  const { slug } = useParams()
  const scope = useApiData(kind === 'brand' ? `brand:${slug}` : null, (signal) => getBrandBySlug(slug, { signal }))
  if (kind === 'brand') {
    if (scope.loading) return <LoadingState />
    if (scope.error) return <ErrorState message={scope.error} onRetry={scope.reload} />
  }
  return <Results title={scope.data?.Name} fixedBrandId={kind === 'brand' ? scope.data.BrandId : undefined} />
}
