import { useEffect } from 'react'
import useApiData from '../../hooks/useApiData.js'
import { listBrands, listCategories } from '../../lib/catalog-api.js'
import CategoryShortcuts from '../components/home/CategoryShortcuts.jsx'
import CategoryShowcase from '../components/home/CategoryShowcase.jsx'
import HeroSection from '../components/home/HeroSection.jsx'
import { BrandSection, NewsSection } from '../components/home/NewsAndBrands.jsx'
import FeaturedProducts from '../components/home/FeaturedProducts.jsx'
import { selectHomeCategories } from '../components/home/categories.js'
import { PolicySection, TrustBar } from '../components/home/StaticSections.jsx'
import './HomePage.css'

// Root categories shown as tabbed product rows, two per section.
const SHOWCASE_CATEGORIES = 4

function pairs(items) {
  const result = []
  for (let index = 0; index < items.length; index += 2) result.push(items.slice(index, index + 2))
  return result
}

// Customer home page (Figma "Trang chủ"), rendered inside CustomerLayout. Every list comes from the public
// catalog/content API; sections below the fold load when the visitor scrolls near them.
export default function HomePage() {
  const categories = useApiData('root-categories', (signal) => listCategories({ rootsOnly: true, signal }))
  const brands = useApiData('brands', (signal) => listBrands({ signal }))
  const roots = categories.data ?? []
  const shortcuts = selectHomeCategories(roots, ['phone', 'laptop', 'accessories', 'smartHome'], 4)
  const showcase = selectHomeCategories(roots, ['phone', 'laptop', 'desktop', 'components'], SHOWCASE_CATEGORIES)

  useEffect(() => {
    document.title = 'VieTech'
  }, [])

  return <div className="home">
    <h1 className="sr-only">VieTech – Mua sắm công nghệ chính hãng</h1>
    <HeroSection categories={categories} brandPool={brands} />
    <TrustBar />
    <CategoryShortcuts categories={{ ...categories, data: shortcuts }} />
    <FeaturedProducts />
    {pairs(showcase).map((group) => <CategoryShowcase key={group[0].CategoryId} categories={group} brandPool={brands} />)}
    <NewsSection />
    <PolicySection />
    <BrandSection brands={brands} />
  </div>
}
