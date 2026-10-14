import { useId, useState } from 'react'
import EmptyState from '../../../components/shared/EmptyState.jsx'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import { listProductSummaries, loadProductCards, searchProducts } from '../../../lib/catalog-api.js'
import ProductCard, { ProductCardSkeleton } from '../ProductCard.jsx'

const COUNT = 5
const SORT_OPTIONS = [
  { value: 'newest', label: 'Mới nhất' },
  { value: 'best_selling', label: 'Bán chạy' },
]

// Newest uses the existing server order. Best-selling compares all public summary pages in the frontend.
export default function FeaturedProducts() {
  const [sort, setSort] = useState('newest')
  const tabsId = useId()
  const panelId = `${tabsId}-products`
  const products = useApiData(`featured-products:${sort}`, async (signal) => {
    let summaries
    if (sort === 'best_selling') {
      summaries = await listProductSummaries({ signal })
      summaries.sort((left, right) => Number(right.SoldQuantity || 0) - Number(left.SoldQuantity || 0))
      summaries = summaries.slice(0, COUNT)
    } else {
      summaries = (await searchProducts({ pageSize: COUNT, signal })).Items
    }
    return loadProductCards(summaries, { signal })
  })

  function onTabKey(event, index) {
    const next = { ArrowRight: (index + 1) % SORT_OPTIONS.length,
      ArrowLeft: (index + SORT_OPTIONS.length - 1) % SORT_OPTIONS.length,
      Home: 0, End: SORT_OPTIONS.length - 1 }[event.key]
    if (next === undefined) return
    event.preventDefault()
    setSort(SORT_OPTIONS[next].value)
    document.getElementById(`${tabsId}-${SORT_OPTIONS[next].value}`)?.focus()
  }

  let content
  if (products.loading) {
    content = <ul className="home-grid" aria-hidden="true">
      {Array.from({ length: COUNT }, (_, index) => <li key={index}><ProductCardSkeleton /></li>)}
    </ul>
  } else if (products.error) {
    content = <ErrorState title="Không tải được sản phẩm" message={products.error} onRetry={products.reload} className="py-8" />
  } else if (!products.data.length) {
    content = <EmptyState headingLevel={3} title="Chưa có sản phẩm đang bán" description="Sản phẩm mới sẽ xuất hiện tại đây." className="py-8" />
  } else {
    content = <ul className="home-grid">
      {products.data.map((product) => <li key={product.id}><ProductCard product={product} /></li>)}
    </ul>
  }

  return <section className="home-products home-card" aria-labelledby="home-featured-title">
    <div className="home-section-head">
      <h2 id="home-featured-title" className="home-title">Sản phẩm nổi bật</h2>
      <div className="home-sort-tabs" role="tablist" aria-label="Sắp xếp sản phẩm nổi bật">
        {SORT_OPTIONS.map((option, index) => <button key={option.value} id={`${tabsId}-${option.value}`}
          type="button" role="tab" className="home-tab home-sort-tab" aria-selected={sort === option.value}
          aria-controls={panelId} tabIndex={sort === option.value ? 0 : -1}
          onClick={() => setSort(option.value)} onKeyDown={(event) => onTabKey(event, index)}>
          {option.label}
        </button>)}
      </div>
    </div>
    <div id={panelId} role="tabpanel" aria-labelledby={`${tabsId}-${sort}`}>{content}</div>
  </section>
}
