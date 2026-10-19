import { Link } from 'react-router-dom'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import { listCategories } from '../../lib/catalog-api.js'
import { categoryPath } from '../routes/paths.js'

export default function CategoryNavigation({ category }) {
  const categories = useApiData('catalog-category-navigation', (signal) => listCategories({ signal }))
  if (categories.loading) return <LoadingState label="Đang tải nhóm sản phẩm…" />
  if (categories.error) return <ErrorState message={categories.error} onRetry={categories.reload} />

  const items = categories.data ?? []
  const children = items.filter((item) => item.ParentCategoryId === category.CategoryId)
  const parent = items.find((item) => item.CategoryId === category.ParentCategoryId)
  const group = children.length ? category : parent
  const options = (children.length ? children : items.filter((item) => item.ParentCategoryId === parent?.CategoryId))
    .toSorted((a, b) => a.DisplayOrder - b.DisplayOrder || a.Name.localeCompare(b.Name, 'vi'))
  if (!group || !options.length) return null

  return <section className="catalog-category-navigation" aria-label="Nhóm sản phẩm">
    <div className="catalog-category-heading">
      <h2>Chọn nhóm sản phẩm</h2>
      <Link to={categoryPath(group.Slug)} aria-current={group.CategoryId === category.CategoryId ? 'page' : undefined}>
        Tất cả {group.Name.toLocaleLowerCase('vi-VN')}
      </Link>
    </div>
    <nav aria-label={`Nhóm ${group.Name.toLocaleLowerCase('vi-VN')}`}>
      <ul>{options.map((item) => <li key={item.CategoryId}>
        <Link to={categoryPath(item.Slug)} aria-current={item.CategoryId === category.CategoryId ? 'page' : undefined}>
          {item.ImageUrl && <img src={item.ImageUrl} alt="" width="48" height="48" loading="lazy"
            onError={(event) => { event.currentTarget.hidden = true }} />}
          <span>{item.Name}</span>
        </Link>
      </li>)}</ul>
    </nav>
  </section>
}
