import { useEffect } from 'react'
import useApiData from '../../hooks/useApiData.js'
import { listBrands, listCategories } from '../../lib/catalog-api.js'
import CategoryShortcuts from '../components/home/CategoryShortcuts.jsx'
import CategoryShowcase from '../components/home/CategoryShowcase.jsx'
import HeroSection from '../components/home/HeroSection.jsx'
import { BrandSection, NewsSection } from '../components/home/NewsAndBrands.jsx'
import FeaturedProducts from '../components/home/FeaturedProducts.jsx'
import PublicCoupons from '../components/PublicCoupons.jsx'
import { pairHomeCategories, selectHomeCategories } from '../components/home/categories.js'
import { PolicySection, TrustBar } from '../components/home/StaticSections.jsx'
import './HomePage.css'

// Customer home page (Figma "Trang chủ"), rendered inside CustomerLayout. Every list comes from the public
// catalog/content API; sections below the fold load when the visitor scrolls near them.
export default function HomePage() {
  const categories = useApiData('root-categories', (signal) => listCategories({ rootsOnly: true, signal }))
  const brands = useApiData('brands', (signal) => listBrands({ signal }))
  const roots = categories.data ?? []
  // Every root category gets a shortcut card, the design's groups first.
  const shortcuts = selectHomeCategories(roots, ['phone', 'laptop', 'accessories', 'smartHome'])
  // Every root category gets a tabbed product row, paired with a related one when there is one.
  const showcase = pairHomeCategories(roots)

  useEffect(() => {
    document.title = 'VieTech'
  }, [])

  return <div className="home">
    <h1 className="sr-only">VieTech – Mua sắm công nghệ chính hãng</h1>
    <HeroSection categories={categories} brandPool={brands} />
    <TrustBar />
    <CategoryShortcuts categories={{ ...categories, data: shortcuts }} />
    <PublicCoupons />
    <FeaturedProducts />
    {showcase.map((group) => <CategoryShowcase key={group[0].CategoryId} categories={group} brandPool={brands} />)}
    <NewsSection />
    <PolicySection />
    <BrandSection brands={brands} />
  </div>
}
