import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import { listBanners } from '../../../lib/catalog-api.js'
import { categoryPath } from '../../routes/paths.js'
import { CategoryIcon, ChevronLeftIcon, ChevronRightIcon } from '../icons.jsx'
import StoreImage from '../StoreImage.jsx'

const SLIDE_MS = 5000

// Left column of the hero: root categories (Figma "Category Sidebar").
function CategoryMenu({ categories }) {
  let content
  if (categories.loading) {
    content = <ul className="home-catmenu-list" aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => <li key={index}><span className="home-catmenu-item is-skeleton" /></li>)}
    </ul>
  } else if (categories.error) {
    content = <div className="home-catmenu-note" role="alert">
      <p>Không tải được danh mục.</p>
      <button type="button" onClick={categories.reload}>Thử lại</button>
    </div>
  } else if (!categories.data.length) {
    content = <p className="home-catmenu-note">Chưa có danh mục sản phẩm.</p>
  } else {
    content = <ul className="home-catmenu-list">
      {categories.data.map((category) => <li key={category.CategoryId}>
        <Link className="home-catmenu-item" to={categoryPath(category.Slug)}>
          <span className="home-catmenu-icon"><CategoryIcon name={category.Name} /></span>
          <span>{category.Name}</span>
        </Link>
      </li>)}
    </ul>
  }
  return <nav className="home-catmenu" aria-label="Danh mục sản phẩm">{content}</nav>
}

// LinkUrl is https or an internal path starting with "/" (ContentService); anything else is not a link.
function BannerLink({ banner, className, children }) {
  const url = banner.LinkUrl ?? ''
  if (url.startsWith('/') && !url.startsWith('//')) return <Link className={className} to={url}>{children}</Link>
  if (url.startsWith('https://')) return <a className={className} href={url}>{children}</a>
  return <div className={className}>{children}</div>
}

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

// Banners from GET /banners (active, in their display window, by DisplayOrder). Advances every 5 s unless the
// visitor hovers or focuses it, or prefers reduced motion.
function BannerCarousel({ banners }) {
  const [index, setIndex] = useState(0)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const paused = hovered || focused
  const count = banners.length
  const current = Math.min(index, count - 1)

  useEffect(() => {
    if (count < 2 || paused || prefersReducedMotion()) return undefined
    const timer = window.setInterval(() => setIndex((value) => (value + 1) % count), SLIDE_MS)
    return () => window.clearInterval(timer)
  }, [count, paused])

  const go = (step) => setIndex((current + step + count) % count)

  return <div className="home-banner-carousel" role="region" aria-roledescription="carousel" aria-label="Chương trình nổi bật"
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
    onFocus={() => setFocused(true)} onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false)
    }}>
    <div className="home-banner">
      <div className="home-banner-track" style={{ transform: `translateX(-${current * 100}%)` }}>
        {banners.map((banner, position) => <div key={banner.BannerId} className="home-banner-slide" role="group"
          aria-roledescription="slide" aria-label={`${position + 1} / ${count}`} inert={position !== current}>
          <BannerLink banner={banner} className="home-banner-link">
            <StoreImage src={banner.ImageUrl} alt={banner.Title} loading={position ? 'lazy' : 'eager'}
              fallback={<BannerPlaceholder>
                <p>{banner.Title}</p>
                <p role="status">Hình ảnh đang được cập nhật.</p>
              </BannerPlaceholder>} />
          </BannerLink>
        </div>)}
      </div>
      {count > 1 && <>
        <button type="button" className="home-banner-nav is-prev" onClick={() => go(-1)} aria-label="Banner trước"><ChevronLeftIcon /></button>
        <button type="button" className="home-banner-nav is-next" onClick={() => go(1)} aria-label="Banner tiếp theo"><ChevronRightIcon /></button>
      </>}
    </div>
    {count > 1 && <div className="home-banner-dots">
        {banners.map((banner, position) => <button key={banner.BannerId} type="button" className="home-banner-dot"
          aria-label={`Xem banner ${position + 1}`} aria-current={position === current || undefined}
          onClick={() => setIndex(position)} />)}
      </div>}
  </div>
}

function BannerPlaceholder({ children, error = false }) {
  return <div className={`home-banner home-banner-placeholder${error ? ' is-error' : ''}`}>{children}</div>
}

// Figma "Danh mục": category menu and the banner area.
export default function HeroSection({ categories }) {
  const banners = useApiData('banners', (signal) => listBanners({ signal }))

  let banner
  if (banners.loading) banner = <div className="home-banner is-skeleton" aria-hidden="true" />
  else if (banners.error) banner = <BannerPlaceholder error>
    <ErrorState title="Không tải được banner" message={banners.error} onRetry={banners.reload} className="py-4" />
  </BannerPlaceholder>
  else if (banners.data?.length) banner = <BannerCarousel banners={banners.data} />
  else banner = <BannerPlaceholder><p role="status">Chưa có chương trình nổi bật.</p></BannerPlaceholder>

  return <section className="home-hero home-card is-raised" aria-label="Danh mục và chương trình nổi bật">
    <CategoryMenu categories={categories} />
    <div className="home-hero-content">{banner}</div>
  </section>
}
