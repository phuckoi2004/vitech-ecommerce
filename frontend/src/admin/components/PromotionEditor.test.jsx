import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import PromotionEditor from './PromotionEditor.jsx'

const categories = [
  { CategoryId: 'laptops', Name: 'Laptop' },
  { CategoryId: 'gaming', Name: 'Laptop gaming', ParentCategoryId: 'laptops' },
  { CategoryId: 'study', Name: 'Laptop học tập', ParentCategoryId: 'laptops' },
  { CategoryId: 'office', Name: 'Laptop văn phòng', ParentCategoryId: 'laptops' },
  { CategoryId: 'pro', Name: 'Gaming cao cấp', ParentCategoryId: 'gaming' },
  { CategoryId: 'phones', Name: 'Điện thoại' },
]
const products = [
  { ProductId: 'p1', CategoryId: 'gaming', Name: 'Máy gaming A' },
  { ProductId: 'p2', CategoryId: 'study', Name: 'Máy học tập B' },
  { ProductId: 'p3', CategoryId: 'office', Name: 'Máy văn phòng C' },
  { ProductId: 'p4', CategoryId: 'pro', Name: 'Máy gaming Pro' },
  { ProductId: 'p5', CategoryId: 'phones', Name: 'Điện thoại D' },
]
const saved = { Name: 'Giảm laptop', Status: 'Draft', DiscountType: 'Percentage', DiscountValue: '10', MinOrderValue: '0', StartDate: '2026-12-01T00:00:00Z', EndDate: '2026-12-31T00:00:00Z', Products: [], Categories: [{ CategoryId: 'gaming' }, { CategoryId: 'pro' }, { CategoryId: 'study' }] }

function editor(row) {
  const onSave = vi.fn()
  render(<PromotionEditor row={row} products={products} categories={categories} onSave={onSave} onClose={vi.fn()} />)
  return onSave
}
function categoryPicker() {
  fireEvent.click(screen.getByRole('button', { name: 'Danh mục áp dụng' }))
  return within(screen.getByRole('group', { name: 'Chọn danh mục khuyến mãi' }))
}
function fillNew() {
  for (const [label, value] of [['Tên chương trình', 'Giảm laptop'], ['Giá trị giảm', '10'], ['Bắt đầu', '2026-12-01T00:00:00'], ['Kết thúc', '2026-12-31T00:00:00']]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

test.each([
  { names: ['Laptop gaming', 'Laptop học tập'], ids: ['gaming', 'pro', 'study'] },
  { names: ['Laptop gaming', 'Laptop học tập', 'Laptop văn phòng'], ids: ['gaming', 'pro', 'study', 'office'] },
])('create a promotion for $names together without adding their parent or other categories', ({ names, ids }) => {
  const onSave = editor()
  fillNew()
  const picker = categoryPicker()
  for (const name of names) fireEvent.click(picker.getByRole('checkbox', { name, exact: true }))
  expect(picker.getByRole('checkbox', { name: 'Laptop', exact: true })).not.toBeChecked()
  expect(picker.getByRole('checkbox', { name: 'Điện thoại', exact: true })).not.toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Danh mục áp dụng' }))
  fireEvent.click(screen.getByRole('button', { name: 'Thêm khuyến mãi mới' }))
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ ProductIds: [], CategoryIds: ids }))
})

test('reopening multiple categories restores both selections and preserves the saved scope on a name-only edit', () => {
  const onSave = editor(saved)
  expect(screen.getByRole('button', { name: 'Danh mục áp dụng' })).toHaveTextContent('Laptop gaming, Laptop học tập')
  const picker = categoryPicker()
  expect(picker.getByRole('checkbox', { name: 'Laptop gaming', exact: true })).toBeChecked()
  expect(picker.getByRole('checkbox', { name: 'Laptop học tập', exact: true })).toBeChecked()
  expect(picker.getByRole('checkbox', { name: 'Gaming cao cấp' })).toBeChecked()
  expect(picker.getByRole('checkbox', { name: 'Gaming cao cấp' })).toBeDisabled()
  expect(picker.getByRole('checkbox', { name: 'Laptop văn phòng' })).not.toBeChecked()
  fireEvent.change(screen.getByLabelText('Tên chương trình'), { target: { value: 'Tên mới' } })
  fireEvent.click(screen.getByRole('button', { name: 'Cập nhật' }))
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ Name: 'Tên mới', CategoryIds: ['gaming', 'pro', 'study'], ProductIds: [] }))
})

test('choose individual products across both selected categories without discounting the entire categories', () => {
  const onSave = editor(saved)
  fireEvent.click(screen.getByRole('button', { name: 'Sản phẩm áp dụng' }))
  expect(screen.getByRole('checkbox', { name: 'Máy gaming Pro' })).toBeInTheDocument()
  expect(screen.queryByRole('checkbox', { name: 'Máy văn phòng C' })).not.toBeInTheDocument()
  expect(screen.queryByRole('checkbox', { name: 'Điện thoại D' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Máy gaming A' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Máy học tập B' }))
  fireEvent.click(screen.getByRole('button', { name: 'Cập nhật' }))
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ ProductIds: ['p1', 'p2'], CategoryIds: [] }))
})

test('reopening a cross-category product subset keeps the exact products selected', () => {
  const onSave = editor({ ...saved, Categories: [], Products: [{ ProductId: 'p1' }, { ProductId: 'p2' }] })
  expect(screen.getByRole('button', { name: 'Danh mục áp dụng' })).toHaveTextContent('Laptop gaming, Laptop học tập')
  fireEvent.click(screen.getByRole('button', { name: 'Sản phẩm áp dụng' }))
  expect(screen.getByRole('checkbox', { name: 'Máy gaming A' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Máy học tập B' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Máy gaming Pro' })).not.toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Tất cả sản phẩm' })).not.toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Cập nhật' }))
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ ProductIds: ['p1', 'p2'], CategoryIds: [] }))
})

test('removing every category blocks saving instead of silently applying to the whole store', () => {
  const onSave = editor(saved), picker = categoryPicker()
  fireEvent.click(picker.getByRole('checkbox', { name: 'Laptop gaming', exact: true }))
  fireEvent.click(picker.getByRole('checkbox', { name: 'Laptop học tập', exact: true }))
  expect(screen.getByRole('button', { name: 'Sản phẩm áp dụng' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Cập nhật' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Vui lòng chọn danh mục áp dụng.')
  expect(onSave).not.toHaveBeenCalled()
})

test('selecting a parent includes descendants once and leaves other root categories out', () => {
  const onSave = editor(saved), picker = categoryPicker()
  fireEvent.click(picker.getByRole('checkbox', { name: 'Laptop', exact: true }))
  expect(picker.getByRole('checkbox', { name: 'Laptop gaming', exact: true })).toBeDisabled()
  expect(picker.getByRole('checkbox', { name: 'Laptop văn phòng' })).toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Cập nhật' }))
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ ProductIds: [], CategoryIds: ['laptops', 'gaming', 'study', 'office', 'pro'] }))
})

test('category search accepts unaccented text and Escape closes the picker and restores focus', () => {
  editor(saved)
  const picker = categoryPicker(), search = picker.getByRole('searchbox', { name: 'Tìm danh mục áp dụng' })
  fireEvent.change(search, { target: { value: 'hoc tap' } })
  expect(picker.getByRole('checkbox', { name: 'Laptop học tập' })).toBeChecked()
  expect(picker.queryByRole('checkbox', { name: 'Laptop gaming', exact: true })).not.toBeInTheDocument()
  fireEvent.keyDown(search, { key: 'Escape' })
  expect(screen.queryByRole('group', { name: 'Chọn danh mục khuyến mãi' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Danh mục áp dụng' })).toHaveFocus()
})
