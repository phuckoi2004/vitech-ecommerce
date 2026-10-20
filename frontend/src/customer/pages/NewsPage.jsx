import { Link, useParams, useSearchParams } from 'react-router-dom'
import EmptyState from '../../components/shared/EmptyState.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import Pagination from '../../components/shared/Pagination.jsx'
import NewsArticle from '../components/news/NewsArticle.jsx'
import useApiData from '../../hooks/useApiData.js'
import { getNews, listNews } from '../../lib/catalog-api.js'
import { HOME_PATH, NEWS_PATH, newsPath } from '../routes/paths.js'
import './ShoppingPages.css'

function NewsBreadcrumb({ title }) {
  return <nav className="news-breadcrumb" aria-label="Đường dẫn tin tức"><ol>
    <li><Link to={HOME_PATH}>Trang chủ</Link></li>
    {title ? <>
      <li><Link to={NEWS_PATH}>Tin tức công nghệ</Link></li>
      <li aria-current="page">{title}</li>
    </> : <li aria-current="page">Tin tức công nghệ</li>}
  </ol></nav>
}

export default function NewsPage() {
  const { slug } = useParams()
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1)
  const news = useApiData(`news-page:${slug ?? ''}:${page}`, (signal) => slug
    ? getNews(slug, { signal }) : listNews({ page, pageSize: 12, signal }))
  if (news.loading) return <LoadingState />
  if (news.error) return <ErrorState message={news.error} onRetry={news.reload} />
  if (slug) return <NewsArticle key={slug} article={news.data} slug={slug}
    breadcrumb={<NewsBreadcrumb title={news.data.Title} />} />
  return <div className="shopping-page"><NewsBreadcrumb /><h1>Tin tức công nghệ</h1>
    {news.data.Items.length ? <ul className="shopping-news-list">{news.data.Items.map((article) => <li key={article.NewsArticleId}>
      <Link className="home-news-card" to={newsPath(article.Slug)}>
        {article.ThumbnailUrl && <img src={article.ThumbnailUrl} alt="" loading="lazy" />}
        <h2>{article.Title}</h2><p>{article.Summary}</p>
      </Link>
    </li>)}</ul> : <EmptyState title="Chưa có tin tức" />}
    <Pagination page={page} pageSize={12} total={news.data.Total} onPageChange={(next) => setParams({ page: String(next) })} />
  </div>
}
