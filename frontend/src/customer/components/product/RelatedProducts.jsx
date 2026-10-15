import EmptyState from '../../../components/shared/EmptyState.jsx'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import { loadProductCards, searchProducts } from '../../../lib/catalog-api.js'
import ProductCard, { ProductCardSkeleton } from '../ProductCard.jsx'

export default function RelatedProducts({ product }) {
  const related = useApiData(product.CategoryId ? `related:${product.ProductId}:${product.CategoryId}` : null, async (signal) => {
    const response = await searchProducts({ categoryId: product.CategoryId, pageSize: 6, signal })
    const summaries = (response.Items ?? []).filter((item) => item.ProductId !== product.ProductId).slice(0, 5)
    return loadProductCards(summaries, { signal })
  })
  return <section className="pd-card pd-related" aria-labelledby="pd-related-title">
    <h2 id="pd-related-title">Sản phẩm tương tự</h2>
    {related.loading ? <div className="pd-related-grid grid grid-cols-2 gap-[18px] sm:grid-cols-3 xl:grid-cols-5" aria-label="Đang tải sản phẩm tương tự">
      {Array.from({ length: 5 }, (_, index) => <ProductCardSkeleton key={index} />)}
    </div> : related.error ? <ErrorState message={related.error} onRetry={related.reload} />
      : related.data?.length ? <ul className="pd-related-grid grid grid-cols-2 gap-[18px] sm:grid-cols-3 xl:grid-cols-5">
        {related.data.map((item) => <li key={item.id}><ProductCard product={item} /></li>)}
      </ul> : <EmptyState title="Chưa có sản phẩm tương tự" />}
  </section>
}
