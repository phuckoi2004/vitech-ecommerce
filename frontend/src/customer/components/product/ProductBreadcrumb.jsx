import { Link } from 'react-router-dom'
import useApiData from '../../../hooks/useApiData.js'
import { listCategories } from '../../../lib/catalog-api.js'
import { foldText } from '../../../lib/search-text.js'
import { HOME_PATH, brandPath, categoryPath } from '../../routes/paths.js'

// As on CellphoneS: Trang chủ / Điện thoại / Apple / iPhone 18 / product. The brand opens the root category with that
// brand chosen. Sub-categories that only group a category by need are named after it ("Điện thoại pin trâu") and are
// left out; a product line ("iPhone 18") stays.
export default function ProductBreadcrumb({ product }) {
  const categories = useApiData('categories:all', (signal) => listCategories({ signal }))
  const all = categories.data ?? []
  const chain = []  // root first
  if (!categories.loading && product.Category) {
    let node = all.find((item) => item.CategoryId === product.Category.CategoryId) ?? product.Category
    while (node && chain.length < 10 && !chain.includes(node)) {
      chain.unshift(node)
      node = all.find((item) => item.CategoryId === node.ParentCategoryId)
    }
  }
  const [root, ...below] = chain
  const lines = root ? below.filter((item) => !foldText(item.Name).startsWith(foldText(root.Name))) : []
  const brand = product.Brand
  const brandId = brand?.BrandId ?? product.BrandId
  const brandLink = root?.Slug && brandId ? `${categoryPath(root.Slug)}?brand=${encodeURIComponent(brandId)}`
    : brand?.Slug ? brandPath(brand.Slug) : null

  return <nav className="pd-breadcrumb" aria-label="Đường dẫn sản phẩm"><ol>
    <li><Link to={HOME_PATH}>Trang chủ</Link></li>
    {root && <li>{root.Slug ? <Link to={categoryPath(root.Slug)}>{root.Name}</Link> : root.Name}</li>}
    {brand?.Name && <li>{brandLink ? <Link to={brandLink}>{brand.Name}</Link> : brand.Name}</li>}
    {lines.map((item) => <li key={item.CategoryId}>{item.Slug ? <Link to={categoryPath(item.Slug)}>{item.Name}</Link> : item.Name}</li>)}
    <li aria-current="page">{product.Name}</li>
  </ol></nav>
}
