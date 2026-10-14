import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import iphoneHomeBanner from '../../../assets/storefront/iphone-home-banner.png'
import galaxyFoldHome from '../../../assets/storefront/galaxy-fold-home.png'
import pocoHome from '../../../assets/storefront/poco-home.png'
import useApiData from '../../../hooks/useApiData.js'
import { listBanners } from '../../../lib/catalog-api.js'
import { categoryPath, productPath } from '../../routes/paths.js'
import { CategoryIcon, ChevronLeftIcon, ChevronRightIcon } from '../icons.jsx'
import StoreImage from '../StoreImage.jsx'

const SLIDE_MS = 5000
const DEFAULT_BANNERS = [
  { BannerId: 'home-iphone', Title: 'iPhone 18 Pro', ImageUrl: iphoneHomeBanner, LinkUrl: productPath('iphone-18-pro') },
  { BannerId: 'home-galaxy', Title: 'Galaxy Z Fold8 Ultra', ImageUrl: galaxyFoldHome,
    LinkUrl: productPath('galaxy-z-fold8-ultra'), Theme: 'galaxy', Brand: 'Samsung Galaxy',
    Description: 'Khám phá thế giới điện thoại gập' },
  { BannerId: 'home-poco', Title: 'POCO F9 Ultra', ImageUrl: pocoHome,
    LinkUrl: productPath('poco-f9-ultra'), Theme: 'poco', Brand: 'Xiaomi POCO',
    Description: 'Tìm chiếc điện thoại phù hợp với bạn' },
]

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
            {banner.Theme ? <PhoneBanner banner={banner} eager={position === 0} />
              : <StoreImage src={banner.ImageUrl} alt={banner.Title} loading={position ? 'lazy' : 'eager'}
                fallback={<DefaultBanner />} />}
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

function PhoneBanner({ banner, eager }) {
  return <div className={`home-phone-banner is-${banner.Theme}`}>
    <div className="home-phone-copy">
      <p className="home-phone-brand">{banner.Brand}</p>
      <h2>{banner.Title}</h2>
      <p className="home-phone-description">{banner.Description}</p>
    </div>
    <StoreImage src={banner.ImageUrl} alt={banner.Title} width="300" height="300"
      loading={eager ? 'eager' : 'lazy'} decoding="async" fallback={<DefaultBanner />} />
  </div>
}

// The original iPhone image from Figma (9:83), also used if an API image cannot be loaded.
function DefaultBanner() {
  return <div className="home-default-banner">
    <img src={iphoneHomeBanner} alt="iPhone 18 Pro" width="1036" height="450" decoding="async" />
  </div>
}

// Figma "Danh mục": category menu and the banner area.
export default function HeroSection({ categories }) {
  const banners = useApiData('banners', (signal) => listBanners({ signal }))

  let banner
  if (banners.loading) banner = <div className="home-banner is-skeleton" aria-hidden="true" />
  else if (banners.data?.length) banner = <BannerCarousel banners={banners.data} />
  else banner = <BannerCarousel banners={DEFAULT_BANNERS} />

  return <section className="home-hero home-card is-raised" aria-label="Danh mục và chương trình nổi bật">
    <CategoryMenu categories={categories} />
    <div className="home-hero-content">
      {banners.error && <div className="home-inline-error" role="alert">
        <span>Không tải được banner.</span><button type="button" onClick={banners.reload}>Thử lại</button>
      </div>}
      {banner}
    </div>
  </section>
}
