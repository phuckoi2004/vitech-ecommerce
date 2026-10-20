import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import logoName from '../../../assets/storefront/vietech-wordmark.png'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import { listNews, recordNewsView } from '../../../lib/catalog-api.js'
import { formatDate } from '../../../lib/format.js'
import { NEWS_PATH, newsPath } from '../../routes/paths.js'
import StoreImage from '../StoreImage.jsx'
import { EyeIcon } from '../AuthFields.jsx'
import NewsArticleBody from './NewsArticleBody.jsx'
import ConsultationButton from '../ConsultationButton.jsx'
import './NewsArticle.css'

function NewsSidebar({ news, items }) {
  return <aside className="news-article-sidebar" aria-labelledby="news-related-title">
    <h2 id="news-related-title">Tin tức liên quan</h2>
    {news.loading ? <p className="news-article-sidebar-notice" role="status">Đang tải tin tức…</p>
      : news.error ? <ErrorState className="news-article-sidebar-error" title="Không tải được tin tức"
        message={news.error} onRetry={news.reload} />
      : items.length ? <ul className="news-article-related-list">
        {items.map(item => <li key={item.Slug}>
          <Link to={newsPath(item.Slug)}>
            <h3>{item.Title}</h3>
            {item.Summary && <p>{item.Summary}</p>}
          </Link>
        </li>)}
      </ul> : <p className="news-article-sidebar-notice">Chưa có bài viết khác.</p>}
    <Link className="news-article-back" to={NEWS_PATH}>← Quay lại Tin tức</Link>
  </aside>
}

function MoreNews({ items }) {
  if (!items.length) return null
  return <section className="news-article-more" aria-labelledby="news-more-title">
    <h2 id="news-more-title">Có thể bạn quan tâm</h2>
    <ul className="news-article-cards">
      {items.map(item => <li key={item.Slug}>
        <Link className="news-article-card" to={newsPath(item.Slug)}>
          <span className="news-article-label">Tin công nghệ</span>
          <h3>{item.Title}</h3>
          {item.Summary && <p>{item.Summary}</p>}
        </Link>
      </li>)}
    </ul>
  </section>
}

export default function NewsArticle({ article, slug, breadcrumb }) {
  const [recordedView, setRecordedView] = useState(null)
  const viewRequest = useRef(null)
  const viewCount = recordedView?.slug === slug ? recordedView.count : article.ViewCount
  // StrictMode replays effects in development. Both subscriptions share the same request;
  // a late response from an article that has been left cannot update the current page.
  useEffect(() => {
    let active = true
    if (viewRequest.current?.slug !== slug) viewRequest.current = { slug, promise: recordNewsView(slug) }
    viewRequest.current.promise.then(result => {
      if (active && Number.isSafeInteger(result?.ViewCount) && result.ViewCount >= 0) {
        setRecordedView({ slug, count: result.ViewCount })
      }
    }, () => {}) // Counting being unavailable must not prevent reading the article.
    return () => { active = false }
  }, [slug])
  const news = useApiData(`news-suggestions:${slug}`, signal => listNews({ pageSize: 4, signal }))
  const seen = new Set([slug])
  const items = (news.data?.Items ?? []).filter(item => {
    if (!item.Slug || seen.has(item.Slug) || (article.NewsArticleId && item.NewsArticleId === article.NewsArticleId)) return false
    seen.add(item.Slug)
    return true
  }).slice(0, 3)
  const relatedItems = items.slice(0, 1)
  const moreItems = items.slice(1)

  return <div className="shopping-page news-detail-page">
    {breadcrumb}
    <article className="news-article" aria-labelledby="news-article-title">
      <header className="news-article-header">
        <ConsultationButton className="news-article-label news-consultation-trigger" />
        <h1 id="news-article-title">{article.Title}</h1>
        {article.Summary && <p className="news-article-summary">{article.Summary}</p>}
        <div className="news-article-meta">
          <span className="news-article-publisher">VieTech News</span>
          {article.PublishedAt && <><span aria-hidden="true">•</span><time dateTime={article.PublishedAt}>{formatDate(article.PublishedAt)}</time></>}
          {Number.isSafeInteger(viewCount) && viewCount >= 0 && <><span aria-hidden="true">•</span>
            <span className="news-article-views"><EyeIcon /><span>{viewCount.toLocaleString('vi-VN')} lượt xem</span></span>
          </>}
        </div>
      </header>
      {article.ThumbnailUrl && <div className="news-article-hero">
        <div className="news-article-hero-copy">
          <img className="news-article-hero-logo" src={logoName} alt="VieTech" width="189" height="49" />
          <p className="news-article-hero-title">{article.Title}</p>
        </div>
        <div className="news-article-hero-visual">
          <StoreImage src={article.ThumbnailUrl} alt={article.Title} decoding="async" className="news-article-cover" />
        </div>
      </div>}
      <div className="news-article-columns">
        <NewsArticleBody value={article.Content} />
        <NewsSidebar news={news} items={relatedItems} />
      </div>
    </article>
    <MoreNews items={moreItems} />
  </div>
}
