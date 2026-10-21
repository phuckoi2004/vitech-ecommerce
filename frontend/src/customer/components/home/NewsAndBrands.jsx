import { Link } from 'react-router-dom'
import useApiData from '../../../hooks/useApiData.js'
import useInView from '../../../hooks/useInView.js'
import { listNews } from '../../../lib/catalog-api.js'
import { NEWS_PATH, brandPath, newsPath } from '../../routes/paths.js'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import StoreImage from '../StoreImage.jsx'
import ScrollRail from './ScrollRail.jsx'

const BRAND_LIMIT = 12
const NEWS_LIMIT = 10

// The latest published articles in a scrolling row, with a link to all news. An empty list is different from a
// failed request.
export function NewsSection() {
  const [ref, seen] = useInView()
  const news = useApiData(seen ? 'news' : null, (signal) => listNews({ pageSize: NEWS_LIMIT, signal }))
  const items = news.data?.Items ?? []

  if (!seen || news.loading) return <div ref={ref} className="home-news-placeholder" aria-hidden="true" />
  if (news.error) return <section className="home-news home-card" aria-labelledby="home-news-title">
    <h2 id="home-news-title" className="home-title">Tin tức công nghệ</h2>
    <ErrorState title="Không tải được tin tức" message={news.error} onRetry={news.reload} />
  </section>
  if (!items.length) return null

  return <section className="home-news home-card" aria-labelledby="home-news-title">
    <div className="home-section-head">
      <h2 id="home-news-title" className="home-title">Tin tức công nghệ</h2>
      <Link className="home-viewall" to={NEWS_PATH}>Xem tất cả tin tức<span aria-hidden="true"> ›</span></Link>
    </div>
    <ScrollRail className="home-news-rail">
      {items.map((article) => <li key={article.NewsArticleId}>
        <Link className="home-news-card" to={newsPath(article.Slug)}>
          <span className="home-news-image">
            <StoreImage src={article.ThumbnailUrl} alt="" loading="lazy" decoding="async"
              fallback={<span className="home-image-placeholder" aria-hidden="true">VieTech</span>} />
          </span>
          <h3>{article.Title}</h3>
          {article.Summary && <p>{article.Summary}</p>}
        </Link>
      </li>)}
    </ScrollRail>
  </section>
}

// Figma "Featured Brands": active brands, by logo when one is set.
export function BrandSection({ brands }) {
  const items = (brands.data ?? []).slice(0, BRAND_LIMIT)
  if (brands.error) return <section className="home-brands home-card" aria-labelledby="home-brands-title">
    <h2 id="home-brands-title" className="home-title is-small">Thương hiệu nổi bật</h2>
    <ErrorState title="Không tải được thương hiệu" message={brands.error} onRetry={brands.reload} />
  </section>
  if (!items.length) return null

  return <section className="home-brands home-card" aria-labelledby="home-brands-title">
    <h2 id="home-brands-title" className="home-title is-small">Thương hiệu nổi bật</h2>
    <ul className="home-brand-list">
      {items.map((brand) => <li key={brand.BrandId}>
        <Link className="home-brand" to={brandPath(brand.Slug)} aria-label={brand.Name}>
          <StoreImage src={brand.LogoUrl} alt="" loading="lazy" decoding="async" fallback={<span>{brand.Name}</span>} />
        </Link>
      </li>)}
    </ul>
  </section>
}
