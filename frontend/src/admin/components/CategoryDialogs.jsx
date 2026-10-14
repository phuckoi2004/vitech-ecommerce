import { useState } from 'react'
import Field from '../../components/shared/Field.jsx'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { slugFromName } from '../../lib/admin-products.js'
import { availableParents } from '../lib/categories.js'
import { createCategory, deleteCategory, updateCategory } from '../services/categories.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import Modal from './Modal.jsx'
import { PRODUCT_CONTROL, ProductButton } from './ProductUi.jsx'

function CategoryError({ message }) {
  return message ? <p role="alert" className="mb-4 rounded-[10px] bg-admin-red/5 p-3 text-sm text-admin-red">{message}</p> : null
}

function CategoryEditor({ category, categories, onBusy, onClose, onDone }) {
  const auth = useInternalAuth()
  const [form, setForm] = useState(() => ({
    Name: category?.Name ?? '', Slug: category?.Slug ?? '', Description: category?.Description ?? '',
    ParentCategoryId: category?.ParentCategoryId ?? '', DisplayOrder: category?.DisplayOrder ?? 0, IsActive: category?.IsActive ?? true,
  }))
  const [slugEdited, setSlugEdited] = useState(Boolean(category))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  function change(key, value) {
    setForm((previous) => ({ ...previous, [key]: value, ...(key === 'Name' && !slugEdited ? { Slug: slugFromName(value) } : {}) }))
    if (key === 'Slug') setSlugEdited(true)
    setError('')
  }
  async function save(event) {
    event.preventDefault()
    if (busy) return
    if (!form.Name.trim()) { setError('Tên danh mục không được để trống.'); return }
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.Slug.trim())) { setError('Đường dẫn chỉ gồm chữ thường không dấu, số và dấu gạch ngang.'); return }
    if (form.DisplayOrder === '' || !Number.isSafeInteger(Number(form.DisplayOrder))) { setError('Thứ tự hiển thị phải là số nguyên.'); return }
    const body = { ...form, Name: form.Name.trim(), Slug: form.Slug.trim(), Description: form.Description.trim() || null,
      ParentCategoryId: form.ParentCategoryId || null, DisplayOrder: Number(form.DisplayOrder) }
    setError(''); setBusy(true); onBusy(true)
    try {
      await auth.withAccessToken((token) => category ? updateCategory(token, category.CategoryId, body) : createCategory(token, body))
      onDone(category ? 'Đã cập nhật danh mục.' : 'Đã thêm danh mục.')
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false); onBusy(false) }
  }
  const parents = availableParents(categories.data ?? [], category?.CategoryId)
  return <form onSubmit={save}>
    <CategoryError message={error || categories.error} />
    {categories.error && <ProductButton secondary onClick={categories.refresh}>Thử lại danh sách danh mục</ProductButton>}
    <fieldset disabled={busy} className="grid min-w-0 grid-cols-2 gap-4 border-0 p-0">
      <Field id="category-name" label="Tên danh mục" className="col-span-full" required maxLength={255} value={form.Name} onChange={(event) => change('Name', event.target.value)} />
      <Field id="category-slug" label="Đường dẫn (slug)" className="col-span-full" required maxLength={300} pattern="[a-z0-9]+(-[a-z0-9]+)*" hint="Được gợi ý từ tên danh mục; bạn có thể chỉnh lại." value={form.Slug} onChange={(event) => change('Slug', event.target.value)} />
      <Field id="category-parent" label="Danh mục cha"><select id="category-parent" className={PRODUCT_CONTROL} value={form.ParentCategoryId} disabled={categories.loading || Boolean(categories.error)} onChange={(event) => change('ParentCategoryId', event.target.value)}>
        <option value="">Không có danh mục cha</option>{parents.map((parent) => <option key={parent.CategoryId} value={parent.CategoryId}>{parent.Name}{parent.IsActive ? '' : ' (đã ẩn)'}</option>)}
      </select></Field>
      <Field id="category-order" label="Thứ tự hiển thị" type="number" step={1} required value={form.DisplayOrder} onChange={(event) => change('DisplayOrder', event.target.value)} />
      <Field id="category-description" label="Mô tả" className="col-span-full"><textarea id="category-description" className={PRODUCT_CONTROL} rows={4} value={form.Description} onChange={(event) => change('Description', event.target.value)} /></Field>
      <Field id="category-status" label="Trạng thái" className="col-span-full"><select id="category-status" className={PRODUCT_CONTROL} value={form.IsActive ? 'active' : 'hidden'} onChange={(event) => change('IsActive', event.target.value === 'active')}>
        <option value="active">Đang hiển thị</option><option value="hidden">Đã ẩn</option>
      </select></Field>
    </fieldset>
    <div className="mt-5 flex justify-end gap-2"><ProductButton secondary disabled={busy} onClick={onClose}>Hủy</ProductButton><ProductButton type="submit" loading={busy} disabled={categories.loading || Boolean(categories.error)}>{category ? 'Lưu thay đổi' : 'Thêm danh mục'}</ProductButton></div>
  </form>
}

function CategoryDetails({ category, categories, onEdit, onClose }) {
  const auth = useInternalAuth()
  const parent = category.ParentCategoryId ? categories.data?.find((item) => item.CategoryId === category.ParentCategoryId)?.Name ?? 'Không tìm thấy danh mục cha' : 'Không có danh mục cha'
  return <>
    <h3 className="mb-5 break-words text-lg font-semibold">{category.Name}</h3>
    <dl className="grid grid-cols-2 gap-5">{[['Đường dẫn', category.Slug], ['Trạng thái', category.IsActive ? 'Đang hiển thị' : 'Đã ẩn'], ['Danh mục cha', parent], ['Thứ tự hiển thị', category.DisplayOrder]].map(([label, value]) => <div key={label}><dt className="text-xs text-admin-muted">{label}</dt><dd className="mt-1 break-words text-sm">{value}</dd></div>)}</dl>
    <h4 className="mt-5 text-xs text-admin-muted">Mô tả</h4><p className="mt-1 text-sm whitespace-pre-wrap">{category.Description || 'Chưa có mô tả.'}</p>
    {categories.error && <div className="mt-3"><CategoryError message={categories.error} /><ProductButton secondary onClick={categories.refresh}>Thử lại danh sách danh mục</ProductButton></div>}
    <div className="mt-6 flex justify-end gap-2"><ProductButton secondary onClick={onClose}>Đóng</ProductButton>{auth.permissions.includes('categories:update') && <ProductButton onClick={onEdit}>Sửa danh mục</ProductButton>}</div>
  </>
}

function CategoryDelete({ category, onBusy, onClose, onDone }) {
  const auth = useInternalAuth()
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState(null)
  const blocked = ['category_has_children', 'category_has_products'].includes(failure?.code)
  async function remove(hide = false) {
    if (busy) return
    setBusy(true); onBusy(true); setFailure(null)
    try {
      await auth.withAccessToken((token) => hide ? updateCategory(token, category.CategoryId, { IsActive: false }) : deleteCategory(token, category.CategoryId))
      onDone(hide ? 'Đã ẩn danh mục.' : 'Đã xóa danh mục.')
    } catch (error) { setFailure(error) }
    finally { setBusy(false); onBusy(false) }
  }
  return <>
    <CategoryError message={failure?.message} />
    <p>Bạn muốn xóa danh mục <strong className="break-words">{category.Name}</strong>?</p>
    <p className="mt-3 text-xs leading-relaxed text-admin-muted">Chỉ xóa được danh mục không còn danh mục con và sản phẩm liên quan. Nếu muốn tạm ngừng hiển thị, hãy đổi trạng thái thành “Đã ẩn”.</p>
    <div className="mt-6 flex justify-end gap-2"><ProductButton secondary disabled={busy} onClick={onClose}>Hủy</ProductButton>
      {blocked && category.IsActive && auth.permissions.includes('categories:update') && <ProductButton secondary disabled={busy} onClick={() => remove(true)}>Ẩn danh mục</ProductButton>}
      <ProductButton loading={busy} className="border-admin-red! bg-admin-red! enabled:hover:bg-admin-red/90!" onClick={() => remove()}>Xác nhận xóa</ProductButton>
    </div>
  </>
}

export default function CategoryDialog({ mode, categoryId, categories, onClose, onDone, onEdit }) {
  const detail = useAdminQuery('/categories/' + encodeURIComponent(categoryId ?? ''), { active_only: false }, mode !== 'new')
  const [busy, setBusy] = useState(false)
  const title = { new: 'Thêm danh mục', edit: 'Sửa danh mục', view: 'Chi tiết danh mục', delete: 'Xóa danh mục' }[mode]
  return <Modal variant="tailwind" open wide={mode !== 'delete'} title={title} busy={busy} onClose={onClose}>
    {mode !== 'new' && detail.loading ? <LoadingState label="Đang tải danh mục…" /> : mode !== 'new' && detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} /> : mode === 'view' && detail.data ? <CategoryDetails category={detail.data} categories={categories} onClose={onClose} onEdit={onEdit} /> : mode === 'delete' && detail.data ? <CategoryDelete category={detail.data} onBusy={setBusy} onClose={onClose} onDone={onDone} /> : (mode === 'new' || detail.data) ? <CategoryEditor category={detail.data} categories={categories} onBusy={setBusy} onClose={onClose} onDone={onDone} /> : null}
  </Modal>
}
