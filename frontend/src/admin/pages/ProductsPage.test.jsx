import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { formatMoney } from '../../lib/format.js'
import { makeAuth } from '../../test/auth.js'
import ProductsPage from './ProductsPage.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), uploadProductImage: vi.fn(), createCatalogItem: vi.fn(), updateCatalogItem: vi.fn(), updateCatalogProduct: vi.fn(), createProduct: vi.fn(), updateProduct: vi.fn(), deleteProduct: vi.fn(), createVariant: vi.fn(), updateVariant: vi.fn(), deleteVariant: vi.fn(), addProductImage: vi.fn(), deleteProductImage: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../../services/api/products.js', () => api)
vi.mock('../services/product-media.js', () => ({ uploadProductImage: api.uploadProductImage }))
const stockApi = vi.hoisted(() => ({ setStockQuantity: vi.fn() }))
vi.mock('../services/inventory.js', () => stockApi)

const productId = '12345678-1111-4111-8111-111111111111'
const variant = { ProductVariantId: 'v1', ProductId: productId, Sku: 'PHONE-256', VariantName: '256GB đen', Price: '10000000.00', StockQuantity: 3, MinStockLevel: 5, Color: 'Đen', Storage: '256GB', IsActive: true, IsSerialTracked: false, IsDeleted: false }
const sibling = { ...variant, ProductVariantId: 'v2', Sku: 'PHONE-512', VariantName: '512GB trắng', Price: '12000000.00', StockQuantity: 17, Color: 'Trắng', Storage: '512GB' }
const product = { ProductId: productId, Name: 'Điện thoại thật', Slug: 'dien-thoai-that', CategoryId: 'c1', BrandId: 'b1', Category: { Name: 'Điện thoại' }, Brand: { Name: 'Hãng thật' }, Status: 'Active', WarrantyMonths: 12, SoldQuantity: 0, Description: null, Specifications: null, Variants: [variant, sibling], Images: [], ThumbnailUrl: null }
const variantRow = (item) => ({ ...item, Name: product.Name, Category: product.Category, Brand: product.Brand, Status: product.Status, ThumbnailUrl: null, IsLowStock: item.StockQuantity > 0 && item.MinStockLevel > 0 && item.StockQuantity <= item.MinStockLevel })
const permissions = ['admin.portal', 'products:view', 'products:create', 'products:update', 'products:delete']
let items, total, variantDetails, parentDetails, parentTotal

function renderPage(path = '/admin/products', granted = permissions) {
  const router = createMemoryRouter([{ path: '/admin/products', element: <ProductsPage /> }], { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Admin', permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

function seedVariants() {
  items = [variantRow(variant), variantRow(sibling)]
  total = items.length
}

beforeEach(() => {
  vi.clearAllMocks()
  api.uploadProductImage.mockReset()
  items = []; total = 0
  parentDetails = new Map([[productId, { ...product }]])
  parentTotal = 1
  variantDetails = new Map([variant, sibling].map((item) => [item.ProductVariantId, { ...product, ...item }]))
  api.getAdminData.mockImplementation(async (token, path) => {
    if (path === '/categories') return [{ CategoryId: 'c1', Name: 'Điện thoại', IsActive: true }]
    if (path === '/brands') return [{ BrandId: 'b1', Name: 'Hãng thật', IsActive: true }]
    if (path === '/admin/variants') return { Items: items, Total: total }
    if (path === '/admin/products') return { Items: [...parentDetails.values()], Total: parentTotal }
    if (path.startsWith('/admin/products/')) return parentDetails.get(path.slice('/admin/products/'.length))
    if (path.startsWith('/admin/catalog-items/')) return variantDetails.get(path.slice('/admin/catalog-items/'.length))
    throw new Error('Unexpected request: ' + path)
  })
  api.createCatalogItem.mockImplementation(async (token, body) => {
    const { Product, ProductId, ...variantBody } = body
    const parent = Product ? { ...product, ...Product, ProductId: 'new-product-id' } : parentDetails.get(ProductId)
    parentDetails.set(parent.ProductId, parent)
    const saved = { ...parent, ...variantBody, StockQuantity: 0, ProductVariantId: 'new-id-' + api.createCatalogItem.mock.calls.length }
    variantDetails.set(saved.ProductVariantId, saved)
    items = [...items, saved]; total = items.length
    return saved
  })
  api.updateCatalogItem.mockImplementation(async (token, id, body) => {
    const saved = { ...variantDetails.get(id), ...body }
    variantDetails.set(id, saved)
    items = items.map((item) => item.ProductVariantId === id ? saved : item)
    return saved
  })
  api.updateCatalogProduct.mockImplementation(async (token, id, body) => {
    const parent = { ...parentDetails.get(id), ...body }
    parentDetails.set(id, parent)
    variantDetails.forEach((item, key) => { if (item.ProductId === id) variantDetails.set(key, { ...item, ...body }) })
    items = items.map((item) => item.ProductId === id ? { ...item, ...body } : item)
    return parent
  })
  api.deleteVariant.mockImplementation(async (token, id) => {
    items = items.filter((item) => item.ProductVariantId !== id)
    total = items.length
  })
})

test.each([
  [20, false, true, 'Đang bán', 'text-green-600'],
  [3, true, true, 'Sắp hết', 'text-amber-600'],
  [0, true, true, 'Hết hàng', 'text-admin-red'],
  [20, false, false, 'Tạm ẩn', 'text-admin-muted'],
])('detail stock=%s low=%s active=%s uses the correct status color', async (StockQuantity, IsLowStock, IsActive, label, color) => {
  variantDetails.set('v1', { ...variantDetails.get('v1'), StockQuantity, IsLowStock, IsActive })
  renderPage('/admin/products?dialog=view&variant=v1')
  const detail = within(await screen.findByRole('region', { name: 'Chi tiết sản phẩm' }, { timeout: 5000 }))
  // Stock quantity shows its own label, so check the badge in the "Trạng thái" field.
  const status = within(detail.getByText('Trạng thái', { selector: 'dt' }).nextElementSibling)
  expect(status.getByText(label)).toHaveClass(color)
})

test('Admin edits stock directly in the variant input; the misplaced detail button is removed', async () => {
  seedVariants()
  stockApi.setStockQuantity.mockImplementation(async (_, id, body) => {
    const saved = { ...variantDetails.get(id), StockQuantity: body.StockQuantity, IsLowStock: false }
    variantDetails.set(id, saved)
    items = items.map((item) => item.ProductVariantId === id ? { ...item, StockQuantity: body.StockQuantity, IsLowStock: false } : item)
    return { ProductVariantId: id, StockQuantity: body.StockQuantity }
  })
  const router = renderPage('/admin/products?dialog=view&variant=v1', [...permissions, 'inventory:update'])
  const detail = within(await screen.findByRole('region', { name: 'Chi tiết sản phẩm' }))
  expect(detail.queryByRole('button', { name: 'Điều chỉnh tồn kho' })).not.toBeInTheDocument()
  fireEvent.click(detail.getByRole('button', { name: 'Sửa chi tiết sản phẩm' }))
  const form = within(await screen.findByRole('region', { name: 'Cập nhật sản phẩm' }))
  const quantity = form.getByRole('spinbutton', { name: 'Số lượng tồn kho', exact: true })
  expect(quantity).not.toHaveAttribute('readonly')
  fireEvent.click(form.getByRole('button', { name: 'Tăng tồn kho 1' }))
  expect(quantity).toHaveValue(4)
  fireEvent.change(quantity, { target: { value: '8' } })
  fireEvent.change(form.getByLabelText('Mã sản phẩm (SKU)'), { target: { value: 'UNSAVED-SKU' } })
  expect(form.getByRole('button', { name: 'Lưu thay đổi' })).toBeDisabled()
  fireEvent.click(form.getByRole('button', { name: 'Lưu tồn kho' }))
  await screen.findByText('Đã cập nhật tồn kho từ 3 thành 8.')
  expect(router.state.location.search).toBe('?dialog=edit&variant=v1')
  expect(quantity).toHaveValue(8)
  expect(form.getByLabelText('Mã sản phẩm (SKU)')).toHaveValue('UNSAVED-SKU')
  expect(form.getByRole('button', { name: 'Lưu thay đổi' })).toBeEnabled()
  expect(api.updateCatalogItem).not.toHaveBeenCalled()
  expect(stockApi.setStockQuantity).toHaveBeenCalledExactlyOnceWith('access-for-test', 'v1', { StockQuantity: 8, ExpectedStockQuantity: 3 })
  fireEvent.click(form.getByRole('button', { name: 'Hủy', exact: true }))
  await screen.findByRole('table')
  const row = screen.getByRole('button', { name: 'Xem PHONE-256' }).closest('tr')
  expect(within(row).getAllByRole('cell')[5]).toHaveTextContent('8')
})

test('ticking tracking immediately requires serials on stock save without saving variant changes or backfilling old stock', async () => {
  stockApi.setStockQuantity.mockImplementation(async (_, id, body) => ({ ProductVariantId: id, StockQuantity: body.StockQuantity, IsSerialTracked: true }))
  renderPage('/admin/products?dialog=edit&variant=v1', [...permissions, 'inventory:update'])
  const form = within(await screen.findByRole('region', { name: 'Cập nhật sản phẩm' }))
  fireEvent.click(form.getByText('Thiết lập biến thể'))
  fireEvent.click(form.getByRole('checkbox', { name: 'Quản lý Serial / IMEI' }))
  fireEvent.click(form.getByRole('button', { name: 'Tăng tồn kho 1' }))
  fireEvent.click(form.getByRole('button', { name: 'Tăng tồn kho 1' }))
  fireEvent.click(form.getByRole('button', { name: 'Lưu tồn kho' }))
  const dialog = within(await screen.findByRole('dialog', { name: 'Nhập Serial/IMEI cho hàng thêm mới' }))
  expect(stockApi.setStockQuantity).not.toHaveBeenCalled()
  expect(api.updateCatalogItem).not.toHaveBeenCalled()
  expect(dialog.getByText(/Cần nhập 2 mã thực tế/)).toBeInTheDocument()
  fireEvent.change(dialog.getByRole('textbox'), { target: { value: 'NEW-1' } })
  fireEvent.click(dialog.getByRole('button', { name: 'Xác nhận sửa' }))
  expect(dialog.getByRole('alert')).toHaveTextContent('đúng 2')
  expect(stockApi.setStockQuantity).not.toHaveBeenCalled()
  fireEvent.change(dialog.getByRole('textbox'), { target: { value: 'NEW-1\nNEW-2' } })
  fireEvent.click(dialog.getByRole('button', { name: 'Xác nhận sửa' }))
  await screen.findByText('Đã cập nhật tồn kho từ 3 thành 5.')
  expect(stockApi.setStockQuantity).toHaveBeenCalledExactlyOnceWith('access-for-test', 'v1', {
    StockQuantity: 5, ExpectedStockQuantity: 3, IsSerialTracked: true, ExpectedIsSerialTracked: false, SerialNumbers: ['NEW-1', 'NEW-2'],
  })
  expect(form.getByRole('button', { name: 'Lưu thay đổi' })).toBeEnabled()
  expect(api.updateCatalogItem).not.toHaveBeenCalled()
})

test('serial input opens only after increasing stock in the variant editor and does not submit the product form', async () => {
  variantDetails.set('v1', { ...variantDetails.get('v1'), IsSerialTracked: true })
  stockApi.setStockQuantity.mockImplementation(async (_, id, body) => ({ ProductVariantId: id, StockQuantity: body.StockQuantity }))
  renderPage('/admin/products?dialog=edit&variant=v1', [...permissions, 'inventory:update'])
  const form = within(await screen.findByRole('region', { name: 'Cập nhật sản phẩm' }))
  fireEvent.click(form.getByRole('button', { name: 'Giảm tồn kho 1' }))
  fireEvent.click(form.getByRole('button', { name: 'Lưu tồn kho' }))
  await screen.findByText('Đã cập nhật tồn kho từ 3 thành 2.')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(form.getByRole('button', { name: 'Tăng tồn kho 1' }))
  fireEvent.click(form.getByRole('button', { name: 'Lưu tồn kho' }))
  const serialDialog = within(await screen.findByRole('dialog', { name: 'Nhập Serial/IMEI cho hàng thêm mới' }))
  expect(serialDialog.getAllByRole('textbox')).toHaveLength(1)
  expect(screen.getByRole('region', { name: 'Cập nhật sản phẩm' }).querySelector('form form')).toBeNull()
  fireEvent.change(serialDialog.getByRole('textbox', { name: 'Serial/IMEI' }), { target: { value: 'NEW-REAL-1' } })
  fireEvent.click(serialDialog.getByRole('button', { name: 'Xác nhận sửa' }))
  await screen.findByText('Đã cập nhật tồn kho từ 2 thành 3.')
  expect(stockApi.setStockQuantity).toHaveBeenNthCalledWith(1, 'access-for-test', 'v1', { StockQuantity: 2, ExpectedStockQuantity: 3 })
  expect(stockApi.setStockQuantity).toHaveBeenNthCalledWith(2, 'access-for-test', 'v1', { StockQuantity: 3, ExpectedStockQuantity: 2, SerialNumbers: ['NEW-REAL-1'] })
  expect(api.updateCatalogItem).not.toHaveBeenCalled()
})

describe('product variant list', () => {
  test('stock warnings remain visible for an inactive variant and distinguish zero, threshold and normal quantities', async () => {
    items = [variantRow({ ...variant, IsActive: false, StockQuantity: 5 }), variantRow({ ...sibling, StockQuantity: 0 }), variantRow({ ...sibling, ProductVariantId: 'v3', Sku: 'SKU-NORMAL', StockQuantity: 6 })]
    total = items.length
    renderPage()
    await screen.findByText('3 biến thể')
    const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(within(rows[0]).getAllByRole('cell')[5]).toHaveTextContent('5Sắp hết')
    expect(within(rows[0]).getByText('Tạm ẩn')).toBeInTheDocument()
    expect(within(rows[1]).getAllByRole('cell')[5]).toHaveTextContent('0Hết hàng')
    expect(within(rows[2]).getAllByRole('cell')[5]).toHaveTextContent('6Còn hàng')
  })
  test('empty data retains all columns and never inserts the Figma example products', async () => {
    renderPage()
    expect(await screen.findByText('Chưa có biến thể phù hợp.')).toBeInTheDocument()
    for (const name of ['Sản phẩm', 'Mã SP', 'Danh mục', 'Thương hiệu', 'Giá bán', 'Tồn kho', 'Trạng thái', 'Thao tác']) expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
    expect(screen.getByText('0 biến thể')).toBeInTheDocument()
    expect(screen.getByText('Hiển thị 0–0 trong 0 biến thể')).toBeInTheDocument()
    expect(screen.queryByText('iPhone 18 Pro Max 256GB')).not.toBeInTheDocument()
    expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/variants', { page: 1, page_size: 8 }, expect.any(AbortSignal))
  })

  test('two variants of the same product have separate rows, SKUs, prices and stock', async () => {
    seedVariants()
    renderPage()
    await screen.findByText('2 biến thể')
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows).toHaveLength(3)
    for (const [index, item] of [variant, sibling].entries()) {
      const cells = within(rows[index + 1]).getAllByRole('cell')
      expect(cells[0]).toHaveTextContent(product.Name)
      expect(cells[0]).toHaveTextContent(item.Color)
      expect(cells[0]).toHaveTextContent(item.Storage)
      expect(cells[1]).toHaveTextContent(item.Sku)
      expect(cells[1]).not.toHaveTextContent(index === 0 ? sibling.Sku : variant.Sku)
      expect(cells[4]).toHaveTextContent(formatMoney(item.Price).replace(/\s+/g, ' '))
      expect(cells[5]).toHaveTextContent(String(item.StockQuantity))
      expect(within(rows[index + 1]).getByRole('button', { name: `Xem ${item.Sku}` })).toBeInTheDocument()
    }
    expect(screen.getByText('Hiển thị 1–2 trong 2 biến thể')).toBeInTheDocument()
    expect(screen.queryByText(product.ProductId)).not.toBeInTheDocument()
    expect(screen.queryByText(product.ProductId.slice(0, 8))).not.toBeInTheDocument()
    expect(api.getAdminData.mock.calls.some(([, path]) => path === '/admin/products')).toBe(false)
  })

  test('view loads only the selected variant and keeps its IDs in the URL', async () => {
    seedVariants()
    const router = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: `Xem ${sibling.Sku}` }))
    const dialog = await screen.findByRole('region', { name: 'Chi tiết sản phẩm' }, { timeout: 5000 })
    expect(await within(dialog).findByText(`Mã sản phẩm: ${sibling.Sku}`)).toBeInTheDocument()
    expect(await within(dialog).findByText(product.Name)).toBeInTheDocument()
    expect(within(dialog).getByText(sibling.Color)).toBeInTheDocument()
    expect(within(dialog).getByText(formatMoney(sibling.Price).replace(/\s+/g, ' '))).toBeInTheDocument()
    expect(within(dialog).queryByText(`Mã sản phẩm: ${variant.Sku}`)).not.toBeInTheDocument()
    expect(within(dialog).queryByText(variant.VariantName)).not.toBeInTheDocument()
    expect(router.state.location.search).not.toContain('product=')
    expect(router.state.location.search).toContain(`variant=${sibling.ProductVariantId}`)
    expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', `/admin/catalog-items/${sibling.ProductVariantId}`, {}, expect.any(AbortSignal))
    expect(api.getAdminData.mock.calls.some(([, path]) => path === `/admin/variants/${variant.ProductVariantId}`)).toBe(false)
  })

  test('filters and pagination query variants and preserve URL state through history', async () => {
    seedVariants(); total = 25
    const router = renderPage('/admin/products?page=2')
    await screen.findByText('25 biến thể')
    expect(screen.getByText('Hiển thị 9–16 trong 25 biến thể')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: 'Danh mục' }), { target: { value: 'c1' } })
    await waitFor(() => expect(router.state.location.search).toBe('?category_id=c1'))
    fireEvent.change(screen.getByRole('combobox', { name: 'Giá bán' }), { target: { value: '5m-15m' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'Tồn kho' }), { target: { value: 'low_stock' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'Trạng thái' }), { target: { value: 'Active' } })
    await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/variants', expect.objectContaining({ category_id: 'c1', min_price: '5000000', max_price: '14999999.99', stock: 'low_stock', status: 'Active', page: 1, page_size: 8 }), expect.any(AbortSignal)))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Trang 2' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Trang 2' }))
    await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/variants', expect.objectContaining({ category_id: 'c1', page: 2 }), expect.any(AbortSignal)))
    await router.navigate(-1)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Trang 1' })).toHaveAttribute('aria-current', 'page'))
    fireEvent.click(screen.getByRole('button', { name: 'Đặt lại' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
    expect(screen.getByRole('combobox', { name: 'Danh mục' })).toHaveValue('')
  })

  test('SKU search is debounced, updates the URL and retains keyboard focus', async () => {
    const router = renderPage()
    await screen.findByText('Chưa có biến thể phù hợp.')
    const input = screen.getByRole('searchbox', { name: 'Tìm sản phẩm, biến thể hoặc SKU' })
    input.focus()
    fireEvent.change(input, { target: { value: sibling.Sku } })
    expect(api.getAdminData.mock.calls.some(([, path, query]) => path === '/admin/variants' && query.keyword === sibling.Sku)).toBe(false)
    await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/variants', expect.objectContaining({ keyword: sibling.Sku }), expect.any(AbortSignal)))
    expect(router.state.location.search).toBe(`?keyword=${sibling.Sku}`)
    expect(input).toHaveFocus()
    expect(input).toHaveValue(sibling.Sku)
  })

  test('a deep link to another filter does not clamp its page using the previous filter total', async () => {
    items = [variantRow(variant)]; total = 1
    const router = renderPage('/admin/products?stock=low_stock')
    await screen.findByText('1 biến thể')
    total = 30
    await router.navigate('/admin/products?page=3')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Trang 3' })).toHaveAttribute('aria-current', 'page'))
    expect(router.state.location.search).toBe('?page=3')
  })

  test('API failure stays visible and retry recovers', async () => {
    const normalRequest = api.getAdminData.getMockImplementation()
    api.getAdminData.mockImplementation(async (...args) => { if (args[1] === '/admin/variants') throw new Error('Không kết nối được máy chủ.'); return normalRequest(...args) })
    renderPage()
    expect(await screen.findByText('Không kết nối được máy chủ.')).toBeInTheDocument()
    expect(screen.queryByText('0 biến thể')).not.toBeInTheDocument()
    api.getAdminData.mockImplementation(normalRequest)
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Chưa có biến thể phù hợp.')).toBeInTheDocument()
  })

  test('view-only staff cannot open variant or parent write forms through the URL', async () => {
    seedVariants()
    const router = renderPage(`/admin/products?dialog=edit&product=${product.ProductId}&variant=${variant.ProductVariantId}`, ['admin.portal', 'products:view'])
    await screen.findByText('2 biến thể')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Thêm sản phẩm|Thêm biến thể|Sửa PHONE|Xóa PHONE/ })).not.toBeInTheDocument()
    for (const mode of ['delete', 'new', 'new-variant', 'edit-product', 'delete-product', 'shared']) {
      await router.navigate(`/admin/products?dialog=${mode}&product=${product.ProductId}&variant=${variant.ProductVariantId}`)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    }
    fireEvent.click(screen.getByRole('button', { name: `Xem ${variant.Sku}` }))
    const dialog = await screen.findByRole('region', { name: 'Chi tiết sản phẩm' })
    await within(dialog).findByText(`Mã sản phẩm: ${variant.Sku}`)
    expect(within(dialog).queryByRole('button', { name: /Sửa sản phẩm|Xóa sản phẩm|Thêm biến thể|Thêm ảnh|Quản lý sản phẩm gốc/ })).not.toBeInTheDocument()
    expect(api.updateCatalogItem).not.toHaveBeenCalled()
    expect(api.deleteVariant).not.toHaveBeenCalled()
  })

  test('new product form creates a Product with its first variant in one request', async () => {
    const router = renderPage()
    await screen.findByText('Chưa có biến thể phù hợp.')
    expect(screen.queryByRole('button', { name: /Thêm biến thể/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Thêm sản phẩm/ }))
    const dialog = await screen.findByRole('region', { name: 'Thêm sản phẩm' }, { timeout: 5000 })
    const user = userEvent.setup()
    await user.type(within(dialog).getByRole('textbox', { name: 'Tên sản phẩm' }), 'Điện thoại mới')
    await user.type(within(dialog).getByRole('textbox', { name: 'Mã sản phẩm (SKU)' }), 'MY-WHITE')
    await user.type(within(dialog).getByRole('textbox', { name: 'Màu sắc' }), 'Trắng')
    // Giá bán là VND nguyên đồng.
    expect(within(dialog).getByRole('spinbutton', { name: 'Giá bán (đồng)' })).toHaveAttribute('step', '1')
    expect(within(dialog).getByRole('spinbutton', { name: 'Giá bán (đồng)' })).toHaveAttribute('max', '9999999999999')
    fireEvent.change(within(dialog).getByRole('spinbutton', { name: 'Giá bán (đồng)' }), { target: { value: '12000000' } })
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'Danh mục' }), { target: { value: 'c1' } })
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'Thương hiệu' }), { target: { value: 'b1' } })
    expect(within(dialog).queryByRole('combobox', { name: 'Sản phẩm gốc' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('textbox', { name: 'Đường dẫn (slug)' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('spinbutton', { name: /^Tồn kho|Giá vốn/ })).not.toBeInTheDocument()
    // Specifications are typed in the description editor, one "Tên: Giá trị" line each.
    const specifications = within(dialog).getByRole('textbox', { name: 'Thông số kỹ thuật' }).editor
    act(() => { specifications.commands.setContent('<p>RAM: 16GB</p><p>Pin 5000 mAh</p>') })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm sản phẩm' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('dòng “Pin 5000 mAh” chưa đúng dạng Tên: Giá trị')
    expect(api.createCatalogItem).not.toHaveBeenCalled()
    act(() => { specifications.commands.setContent('<p>RAM: 16GB</p><ul><li><p>Pin: 5000 mAh</p></li></ul><p>Màn hình: 6.7 inch<br>Tần số quét: 120 Hz</p>') })
    api.uploadProductImage.mockResolvedValueOnce({ ImageUrl: 'https://example.com/white.png' })
    await user.upload(within(dialog).getByLabelText('Tải ảnh sản phẩm'), new File(['image'], 'white.png', { type: 'image/png' }))
    // A photo can also be added by its address, but never twice.
    const address = within(dialog).getByRole('textbox', { name: 'Đường dẫn ảnh sản phẩm' })
    fireEvent.change(address, { target: { value: 'https://example.com/white.png' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm ảnh từ đường dẫn' }))
    expect(within(within(dialog).getByRole('region', { name: 'Bộ ảnh sản phẩm' })).getByRole('alert')).toHaveTextContent('Ảnh này đã có trong bộ ảnh.')
    fireEvent.change(address, { target: { value: 'example.com/back.png' } })
    fireEvent.keyDown(address, { key: 'Enter' })
    expect(within(dialog).getByRole('img', { name: 'Ảnh sản phẩm 2' })).toHaveAttribute('src', 'https://example.com/back.png')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm sản phẩm' }))
    await waitFor(() => expect(api.createCatalogItem).toHaveBeenCalledWith('access-for-test', {
      Sku: 'MY-WHITE', Color: 'Trắng', Storage: null, Price: '12000000', MinStockLevel: 0, IsSerialTracked: false, IsActive: true,
      VariantImageUrls: ['https://example.com/white.png', 'https://example.com/back.png'], DefaultImageUrl: 'https://example.com/white.png', IsDefaultVariant: true,
      Product: { Name: 'Điện thoại mới', CategoryId: 'c1', BrandId: 'b1', WarrantyMonths: 12, Status: 'Draft',
        Description: null, Specifications: { RAM: '16GB', Pin: '5000 mAh', 'Màn hình': '6.7 inch', 'Tần số quét': '120 Hz' },
        Images: [{ ImageUrl: 'https://example.com/white.png', IsDefault: true }, { ImageUrl: 'https://example.com/back.png', IsDefault: false }] },
    }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(router.state.location.search).toBe('')
    expect(await screen.findByRole('button', { name: 'Xem MY-WHITE' })).toBeInTheDocument()
    expect(api.createProduct).not.toHaveBeenCalled()
    expect(api.createVariant).not.toHaveBeenCalled()
  }, 10000)

  test('variant edit submits only variant fields and preserves the parent and other row', async () => {
    seedVariants()
    const router = renderPage('/admin/products?stock=low_stock')
    fireEvent.click(await screen.findByRole('button', { name: 'Sửa ' + variant.Sku }))
    const dialog = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    await within(dialog).findByRole('textbox', { name: 'Mã sản phẩm (SKU)' })
    expect(within(dialog).getByRole('textbox', { name: 'Tên sản phẩm' })).toHaveValue(product.Name)
    expect(within(dialog).getByRole('textbox', { name: 'Tên sản phẩm' })).toBeDisabled()
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Màu sắc' }), { target: { value: 'Xanh' } })
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Mã sản phẩm (SKU)' }), { target: { value: 'PHONE-GREEN' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Xác nhận những thay đổi?' })).getByRole('button', { name: 'Xác nhận' }))
    await waitFor(() => expect(api.updateCatalogItem).toHaveBeenCalledWith('access-for-test', variant.ProductVariantId,
      expect.objectContaining({ Color: 'Xanh', Sku: 'PHONE-GREEN', IsActive: true })))
    const body = api.updateCatalogItem.mock.calls[0][2]
    for (const field of ['StockQuantity', 'CostPrice', 'ProductId', 'Name', 'Images', 'Status']) expect(body).not.toHaveProperty(field)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByRole('button', { name: 'Xem PHONE-GREEN' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Xem ' + sibling.Sku })).toBeInTheDocument()
    expect(variantDetails.get(sibling.ProductVariantId).Color).toBe('Trắng')
    expect(api.updateProduct).not.toHaveBeenCalled()
    expect(api.updateCatalogItem).toHaveBeenCalledTimes(1)
    expect(router.state.location.search).toBe('?stock=low_stock')
  })

  test('failed save retains the input and allows correction and retry', async () => {
    seedVariants()
    api.updateCatalogItem.mockRejectedValueOnce(new Error('SKU đã tồn tại'))
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Sửa ' + variant.Sku }))
    const dialog = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    const sku = await within(dialog).findByRole('textbox', { name: 'Mã sản phẩm (SKU)' })
    fireEvent.change(sku, { target: { value: 'DUPLICATE' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Xác nhận những thay đổi?' })).getByRole('button', { name: 'Xác nhận' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('SKU đã tồn tại')
    expect(sku).toHaveValue('DUPLICATE')
    fireEvent.change(sku, { target: { value: 'UNIQUE' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Xác nhận những thay đổi?' })).getByRole('button', { name: 'Xác nhận' }))
    expect(await screen.findByRole('button', { name: 'Xem UNIQUE' })).toBeInTheDocument()
  })

  test('delete requires confirmation and removes only the selected SKU, retaining filters', async () => {
    seedVariants()
    const router = renderPage('/admin/products?stock=low_stock')
    fireEvent.click(await screen.findByRole('button', { name: 'Xóa ' + variant.Sku }))
    let dialog = await screen.findByRole('dialog', { name: 'Xác nhận xóa sản phẩm?' })
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })).toBeEnabled())
    expect(api.deleteVariant).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Hủy' }))
    expect(api.deleteVariant).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Xóa ' + variant.Sku }))
    dialog = await screen.findByRole('dialog', { name: 'Xác nhận xóa sản phẩm?' })
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })).toBeEnabled())
    fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true }))
    await waitFor(() => expect(api.deleteVariant).toHaveBeenCalledWith('access-for-test', variant.ProductVariantId))
    await screen.findByText('1 biến thể')
    expect(screen.queryByRole('button', { name: 'Xem ' + variant.Sku })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Xem ' + sibling.Sku })).toBeInTheDocument()
    expect(api.deleteProduct).not.toHaveBeenCalled()
    expect(api.deleteVariant).toHaveBeenCalledTimes(1)
    expect(router.state.location.search).toBe('?stock=low_stock')
  })
  test('failed deletion allows retry and prevents repeated submissions or dismissal while pending', async () => {
    seedVariants()
    api.deleteVariant.mockRejectedValueOnce(new Error('Không thể xóa biến thể.'))
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Xóa ' + variant.Sku }))
    const dialog = screen.getByRole('dialog', { name: 'Xác nhận xóa sản phẩm?' })
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })).toBeEnabled())
    fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true }))
    await within(dialog).findByText('Không thể xóa biến thể.')
    expect(items).toHaveLength(2)
    let finish
    api.deleteVariant.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const confirm = within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    expect(api.deleteVariant).toHaveBeenCalledTimes(2)
    expect(within(dialog).getByRole('button', { name: 'Hủy' })).toBeDisabled()
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    expect(dialog).toBeInTheDocument()
    await act(async () => finish(null))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(api.deleteProduct).not.toHaveBeenCalled()
  })

  test('failed selected-item reads cannot be confirmed and can retry without switching SKU', async () => {
    seedVariants()
    const original = api.getAdminData.getMockImplementation()
    let failed = true
    api.getAdminData.mockImplementation((...args) => args[1] === '/admin/catalog-items/v1' && failed ? Promise.reject(new Error('Không tải được sản phẩm.')) : original(...args))
    renderPage('/admin/products?dialog=delete&variant=v1')
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('Không tải được sản phẩm.')
    expect(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })).toBeDisabled()
    expect(api.deleteVariant).not.toHaveBeenCalled()
    failed = false
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thử lại' }))
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })).toBeEnabled())
    fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true }))
    await waitFor(() => expect(api.deleteVariant).toHaveBeenCalledWith('access-for-test', 'v1'))
  })

  test('a deletion response from an earlier dialog never dismisses the newly selected SKU', async () => {
    seedVariants()
    let finish
    api.deleteVariant.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const router = renderPage('/admin/products?dialog=delete&variant=v1')
    const first = await screen.findByRole('dialog')
    await waitFor(() => expect(within(first).getByRole('button', { name: 'Xác nhận', exact: true })).toBeEnabled())
    fireEvent.click(within(first).getByRole('button', { name: 'Xác nhận', exact: true }))
    await act(() => router.navigate('/admin/products?dialog=delete&variant=v2'))
    await act(async () => finish(null))
    expect(router.state.location.search).toBe('?dialog=delete&variant=v2')
    expect(screen.getByRole('dialog', { name: 'Xác nhận xóa sản phẩm?' })).toBeInTheDocument()
  })

  test('adding a color from details presets the same ProductId instead of creating another Product', async () => {
    seedVariants()
    const router = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Xem ' + variant.Sku }))
    const view = await screen.findByRole('region', { name: 'Chi tiết sản phẩm' })
    await within(view).findByText('Mã sản phẩm: ' + variant.Sku)
    fireEvent.click(within(view).getByRole('button', { name: 'Thêm biến thể cùng sản phẩm' }))
    const dialog = await screen.findByRole('region', { name: 'Thêm sản phẩm' })
    await waitFor(() => expect(within(dialog).getByRole('combobox', { name: 'Sản phẩm đã có' })).toHaveValue(productId))
    expect(within(dialog).getByRole('radio', { name: 'Biến thể của sản phẩm đã có' })).toBeChecked()
    expect(within(dialog).getByRole('textbox', { name: 'Tên sản phẩm' })).toBeDisabled()
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Mã sản phẩm (SKU)' }), { target: { value: 'PHONE-PINK' } })
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Màu sắc' }), { target: { value: 'Hồng' } })
    fireEvent.change(within(dialog).getByRole('spinbutton', { name: 'Giá bán (đồng)' }), { target: { value: '11000000' } })
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Thêm sản phẩm' })).toBeEnabled())
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm sản phẩm' }))
    await waitFor(() => expect(api.createCatalogItem).toHaveBeenCalledWith('access-for-test', {
      ProductId: productId, Sku: 'PHONE-PINK', Color: 'Hồng', Storage: null, Price: '11000000',
      MinStockLevel: 0, IsActive: true, IsSerialTracked: false,
      VariantImageUrls: [], DefaultImageUrl: null, IsDefaultVariant: false, AdditionalImages: [],
    }))
    expect(api.createCatalogItem.mock.calls[0][1]).not.toHaveProperty('Product')
    expect(api.createProduct).not.toHaveBeenCalled()
    expect(api.updateCatalogProduct).not.toHaveBeenCalled()
    await screen.findByText('3 biến thể')
    expect(items.map((item) => item.ProductId)).toEqual([productId, productId, productId])
    expect(router.state.location.search).toBe('')
  })

  test('existing product picker searches and pages and supports products with no variants', async () => {
    const bareId = 'bare-product'
    parentDetails.set(bareId, { ...product, ProductId: bareId, Name: 'Mẫu chưa có biến thể', Variants: [] })
    parentTotal = 21
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /Thêm sản phẩm/ }))
    const dialog = screen.getByRole('region', { name: 'Thêm sản phẩm' })
    fireEvent.click(within(dialog).getByRole('radio', { name: 'Biến thể của sản phẩm đã có' }))
    await within(dialog).findByRole('option', { name: 'Mẫu chưa có biến thể' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sau' }))
    await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/products',
      { keyword: '', page: 2, page_size: 20 }, expect.any(AbortSignal)))
    fireEvent.change(within(dialog).getByRole('searchbox', { name: 'Tìm sản phẩm đã có' }), { target: { value: 'Mẫu' } })
    expect(within(dialog).queryByRole('button', { name: 'Tìm', exact: true })).not.toBeInTheDocument()
    await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/products',
      { keyword: 'Mẫu', page: 1, page_size: 20 }, expect.any(AbortSignal)))
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'Sản phẩm đã có' }), { target: { value: bareId } })
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Mã sản phẩm (SKU)' }), { target: { value: 'FIRST-COLOR' } })
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Màu sắc' }), { target: { value: 'Trắng' } })
    fireEvent.change(within(dialog).getByRole('spinbutton', { name: 'Giá bán (đồng)' }), { target: { value: '1000000' } })
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Thêm sản phẩm' })).toBeEnabled())
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thêm sản phẩm' }))
    await waitFor(() => expect(api.createCatalogItem).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ ProductId: bareId, Sku: 'FIRST-COLOR' })))
  })

  test('shared metadata editing is explicit and applies to all variants without moving their IDs', async () => {
    seedVariants()
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Xem ' + variant.Sku }))
    const view = await screen.findByRole('region', { name: 'Chi tiết sản phẩm' })
    await within(view).findByText('Mã sản phẩm: ' + variant.Sku)
    fireEvent.click(within(view).getByRole('button', { name: 'Sửa thông tin chung' }))
    const dialog = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    expect(within(dialog).getByText(/áp dụng cho sản phẩm chung/)).toBeInTheDocument()
    fireEvent.change(await within(dialog).findByRole('textbox', { name: 'Tên sản phẩm' }), { target: { value: 'Tên chung mới' } })
    expect(within(dialog).getByRole('textbox', { name: 'Mã sản phẩm (SKU)' })).toBeDisabled()
    api.uploadProductImage.mockResolvedValueOnce({ ImageUrl: 'https://example.com/shared.png' })
    await userEvent.setup().upload(within(dialog).getByLabelText('Tải ảnh sản phẩm'), new File(['image'], 'shared.png', { type: 'image/png' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
    expect(api.updateCatalogProduct).not.toHaveBeenCalled()
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Xác nhận những thay đổi?' })).getByRole('button', { name: 'Xác nhận' }))
    await waitFor(() => expect(api.updateCatalogProduct).toHaveBeenCalledWith('access-for-test', productId, expect.objectContaining({
      Name: 'Tên chung mới', Status: 'Active', Images: [{ ImageUrl: 'https://example.com/shared.png', IsDefault: true }],
    })))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(items.map((item) => item.Name)).toEqual(['Tên chung mới', 'Tên chung mới'])
    expect(items.map((item) => item.ProductVariantId)).toEqual([variant.ProductVariantId, sibling.ProductVariantId])
    expect(items.map((item) => item.ProductId)).toEqual([productId, productId])
    expect(api.updateCatalogItem).not.toHaveBeenCalled()
  })

  async function openSharedEditor() {
    fireEvent.click(await screen.findByRole('button', { name: 'Xem ' + variant.Sku }))
    const view = await screen.findByRole('region', { name: 'Chi tiết sản phẩm' })
    await within(view).findByText('Mã sản phẩm: ' + variant.Sku)
    return view
  }

  async function saveShared(dialog) {
    fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu thay đổi' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Xác nhận những thay đổi?' })).getByRole('button', { name: 'Xác nhận' }))
    await waitFor(() => expect(api.updateCatalogProduct).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Cập nhật sản phẩm' })).not.toBeInTheDocument(), { timeout: 5000 })
  }

  test('the description editor saves formatted HTML that is shown and edited again with its formatting', async () => {
    seedVariants()
    renderPage()
    fireEvent.click(within(await openSharedEditor()).getByRole('button', { name: 'Sửa thông tin chung' }))
    const dialog = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    const editor = (await within(dialog).findByRole('textbox', { name: 'Mô tả' })).editor
    // The specifications editor below has the same toolbar; use the description's own.
    const tools = within(within(dialog).getByRole('toolbar', { name: 'Định dạng mô tả sản phẩm' }))
    const selectText = (from, to) => act(() => { editor.commands.setTextSelection({ from, to }) })
    act(() => { editor.chain().focus().insertContent('<p>Thiết kế</p><p>Màn hình lớn</p>').run() })
    selectText(1, 9)
    fireEvent.change(tools.getByRole('combobox', { name: 'Cỡ chữ' }), { target: { value: '24px' } })
    fireEvent.change(tools.getByRole('combobox', { name: 'Phông chữ' }), { target: { value: 'Georgia, serif' } })
    fireEvent.click(tools.getByRole('button', { name: 'In đậm (Ctrl + B)' }))
    selectText(20, 23)
    fireEvent.click(tools.getByRole('button', { name: 'In đậm (Ctrl + B)' }))
    act(() => { editor.commands.setTextSelection(23) })
    // The image goes through the existing product image upload endpoint; saving waits for it.
    let finish
    api.uploadProductImage.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    fireEvent.click(tools.getByRole('button', { name: 'Chèn hoặc sửa ảnh' }))
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Mô tả ảnh' }), { target: { value: 'Mặt sau' } })
    const file = new File([new Uint8Array(64)], 'mat-sau.png', { type: 'image/png' })
    fireEvent.change(within(dialog).getByLabelText('Chọn ảnh để chèn vào mô tả'), { target: { files: [file] } })
    await waitFor(() => expect(api.uploadProductImage).toHaveBeenCalledWith('access-for-test', file))
    expect(within(dialog).getByRole('button', { name: 'Lưu thay đổi' })).toBeDisabled()
    await act(async () => { finish({ ImageUrl: 'https://cdn.example/products/mat-sau.png' }) })
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Lưu thay đổi' })).toBeEnabled())
    await saveShared(dialog)
    const html = '<p><span style="font-family: Georgia, serif; font-size: 24px"><strong>Thiết kế</strong></span></p><p>Màn hình <strong>lớn</strong></p>'
      + '<img src="https://cdn.example/products/mat-sau.png" alt="Mặt sau" loading="lazy" decoding="async">'
    expect(api.updateCatalogProduct).toHaveBeenCalledWith('access-for-test', productId, expect.objectContaining({ Description: html }))

    const view = await openSharedEditor()
    expect(within(view).getByText('Thiết kế').parentElement).toHaveStyle({ fontSize: '24px', fontFamily: 'Georgia, serif' })
    expect(within(view).getByText('lớn').tagName).toBe('STRONG')
    expect(within(view).getByRole('img', { name: 'Mặt sau' })).toHaveAttribute('src', 'https://cdn.example/products/mat-sau.png')
    fireEvent.click(within(view).getByRole('button', { name: 'Sửa thông tin chung' }))
    const reopened = await within(await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })).findByRole('textbox', { name: 'Mô tả' })
    expect(reopened.querySelector('span[style]')).toHaveStyle({ fontSize: '24px', fontFamily: 'Georgia, serif' })
    expect(reopened.querySelector('span[style] strong')).toHaveTextContent('Thiết kế')
    expect(reopened.querySelector('img')).toHaveAttribute('alt', 'Mặt sau')
  })

  test('a legacy plain-text description is displayed as paragraphs and saved unchanged when not edited', async () => {
    const legacy = 'Đoạn mô tả cũ.\nDòng thứ hai.\n\nĐoạn <không phải thẻ> thứ hai.'
    for (const map of [parentDetails, variantDetails]) map.forEach((entry, key) => map.set(key, { ...entry, Description: legacy }))
    seedVariants()
    renderPage()
    const view = await openSharedEditor()
    expect(within(view).getByText(/Đoạn mô tả cũ\./).tagName).toBe('P')
    expect(within(view).getByText('Đoạn <không phải thẻ> thứ hai.')).toBeInTheDocument()
    fireEvent.click(within(view).getByRole('button', { name: 'Sửa thông tin chung' }))
    const dialog = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    const description = await within(dialog).findByRole('textbox', { name: 'Mô tả' })
    expect(description.querySelectorAll('p')).toHaveLength(2)
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Tên sản phẩm' }), { target: { value: 'Tên mới' } })
    await saveShared(dialog)
    expect(api.updateCatalogProduct).toHaveBeenCalledWith('access-for-test', productId, expect.objectContaining({ Name: 'Tên mới', Description: legacy }))
  })

  test('canceling update confirmation retains input; pending save blocks duplicate submission and dismissal', async () => {
    seedVariants()
    let finish
    api.updateCatalogItem.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    renderPage('/admin/products?dialog=edit&variant=v1&stock=low_stock')
    const page = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    const sku = within(page).getByLabelText('Mã sản phẩm (SKU)')
    fireEvent.change(sku, { target: { value: 'EDITED' } })
    fireEvent.click(within(page).getByRole('button', { name: 'Lưu thay đổi' }))
    let confirm = screen.getByRole('dialog', { name: 'Xác nhận những thay đổi?' })
    expect(api.updateCatalogItem).not.toHaveBeenCalled()
    fireEvent.click(within(confirm).getByRole('button', { name: 'Hủy' }))
    expect(sku).toHaveValue('EDITED')
    fireEvent.click(within(page).getByRole('button', { name: 'Lưu thay đổi' }))
    confirm = screen.getByRole('dialog', { name: 'Xác nhận những thay đổi?' })
    const yes = within(confirm).getByRole('button', { name: 'Xác nhận' })
    fireEvent.click(yes); fireEvent.click(yes)
    expect(api.updateCatalogItem).toHaveBeenCalledTimes(1)
    expect(within(confirm).getByRole('button', { name: 'Hủy' })).toBeDisabled()
    fireEvent(confirm, new Event('cancel', { cancelable: true }))
    expect(confirm).toBeInTheDocument()
    await act(async () => finish(variant))
    await screen.findByRole('region', { name: 'Quản lý danh sách sản phẩm' })
  })

  test('gallery uses server images, switches thumbnails, and detail deletion still targets one variant', async () => {
    seedVariants()
    variantDetails.set('v1', { ...variantDetails.get('v1'), Images: [{ ImageUrl: 'https://example.com/first.png', IsDefault: false }, { ImageUrl: 'https://example.com/default.png', IsDefault: true }] })
    renderPage('/admin/products?dialog=view&variant=v1')
    const page = await screen.findByRole('region', { name: 'Chi tiết sản phẩm' })
    expect(within(page).getByRole('img', { name: product.Name, exact: true })).toHaveAttribute('src', 'https://example.com/default.png')
    fireEvent.click(within(page).getByRole('button', { name: 'Xem ảnh 1' }))
    expect(within(page).getByRole('img', { name: product.Name, exact: true })).toHaveAttribute('src', 'https://example.com/first.png')
    fireEvent.click(within(page).getByRole('button', { name: 'Xóa sản phẩm' }))
    const confirm = screen.getByRole('dialog', { name: 'Xác nhận xóa sản phẩm?' })
    await waitFor(() => expect(within(confirm).getByRole('button', { name: 'Xác nhận' })).toBeEnabled())
    fireEvent.click(within(confirm).getByRole('button', { name: 'Xác nhận' }))
    await screen.findByText('1 biến thể')
    expect(api.deleteVariant).toHaveBeenCalledWith('access-for-test', 'v1')
    expect(api.deleteProduct).not.toHaveBeenCalled()
  })

  test('file upload validates size/type, blocks save while pending and preserves successful images on later failure', async () => {
    renderPage('/admin/products?dialog=new')
    const page = screen.getByRole('region', { name: 'Thêm sản phẩm' })
    const user = userEvent.setup()
    const input = within(page).getByLabelText('Tải ảnh sản phẩm')
    const large = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' })
    await user.upload(input, large)
    expect(await within(page).findByRole('alert')).toHaveTextContent('tối đa 2 MB')
    expect(api.uploadProductImage).not.toHaveBeenCalled()
    let finish
    api.uploadProductImage.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
      .mockRejectedValueOnce(new Error('Không tải được ảnh thứ hai.'))
    await user.upload(input, [new File(['a'], 'first.png', { type: 'image/png' }), new File(['b'], 'second.webp', { type: 'image/webp' })])
    expect(within(page).getByRole('button', { name: 'Thêm sản phẩm', exact: true })).toBeDisabled()
    expect(within(page).getByRole('button', { name: 'Hủy' })).toBeDisabled()
    await act(async () => finish({ ImageUrl: 'https://example.com/uploaded.png' }))
    expect(await within(page).findByRole('alert')).toHaveTextContent('Không tải được ảnh thứ hai.')
    expect(within(page).getByRole('img', { name: 'Ảnh sản phẩm 1' })).toHaveAttribute('src', 'https://example.com/uploaded.png')
    expect(within(page).getByLabelText('Ảnh mặc định 1')).toBeChecked()
    expect(api.createCatalogItem).not.toHaveBeenCalled()
    api.uploadProductImage.mockResolvedValueOnce({ ImageUrl: 'https://example.com/second.png' })
    await user.upload(input, new File(['c'], 'retry.png', { type: 'image/png' }))
    expect(await within(page).findByRole('img', { name: 'Ảnh sản phẩm 2' })).toHaveAttribute('src', 'https://example.com/second.png')
    expect(within(page).getByLabelText('Ảnh mặc định 1')).toBeChecked()
  })

  test('variant chooses multiple parent images and a representative without changing sibling selections', async () => {
    seedVariants()
    const images = [1, 2, 3].map((id) => ({ ImageUrl: 'https://demo.supabase.co/' + id + '.png', IsDefault: id === 1 }))
    variantDetails.set('v2', { ...variantDetails.get('v2'), Images: images, VariantImages: [], IsDefaultVariant: false })
    renderPage('/admin/products?dialog=edit&variant=v2')
    const page = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    fireEvent.click(within(page).getByLabelText('Chọn ảnh 1 cho biến thể'))
    fireEvent.click(within(page).getByLabelText('Chọn ảnh 3 cho biến thể'))
    fireEvent.click(within(page).getByLabelText('Ảnh đại diện biến thể 3'))
    fireEvent.click(within(page).getByLabelText('Biến thể mặc định'))
    expect(api.updateCatalogItem).not.toHaveBeenCalled()
    fireEvent.click(within(page).getByRole('button', { name: 'Lưu thay đổi' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Xác nhận' }))
    await waitFor(() => expect(api.updateCatalogItem).toHaveBeenCalledWith('access-for-test', 'v2', expect.objectContaining({
      VariantImageUrls: [images[0].ImageUrl, images[2].ImageUrl], DefaultImageUrl: images[2].ImageUrl, IsDefaultVariant: true, AdditionalImages: [],
    })))
    expect(api.updateCatalogProduct).not.toHaveBeenCalled()
    expect(variantDetails.get('v1').Sku).toBe(variant.Sku)
  })

  test('re-saving the variant that is already default does not claim the default again', async () => {
    seedVariants()
    variantDetails.set('v2', { ...variantDetails.get('v2'), IsDefaultVariant: true })
    renderPage('/admin/products?dialog=edit&variant=v2')
    const page = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    expect(within(page).getByLabelText('Biến thể mặc định')).toBeChecked()
    fireEvent.click(within(page).getByRole('button', { name: 'Lưu thay đổi' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Xác nhận' }))
    await waitFor(() => expect(api.updateCatalogItem).toHaveBeenCalledWith('access-for-test', 'v2', expect.objectContaining({ IsDefaultVariant: false })))
  })

  test('photos added while editing a variant are selected for it and saved together, never left for its siblings', async () => {
    seedVariants()
    const shared = { ImageUrl: 'https://demo.supabase.co/black.png', IsDefault: true }
    variantDetails.set('v2', { ...variantDetails.get('v2'), Images: [shared], VariantImages: [], IsDefaultVariant: false })
    renderPage('/admin/products?dialog=edit&variant=v2')
    const page = await screen.findByRole('region', { name: 'Cập nhật sản phẩm' })
    api.uploadProductImage.mockResolvedValueOnce({ ImageUrl: 'https://demo.supabase.co/blue-front.png' })
    await userEvent.setup().upload(within(page).getByLabelText('Tải ảnh sản phẩm'), new File(['a'], 'front.png', { type: 'image/png' }))
    const address = within(page).getByRole('textbox', { name: 'Đường dẫn ảnh sản phẩm' })
    fireEvent.change(address, { target: { value: 'https://cdn.example.test/blue-back.png' } })
    fireEvent.keyDown(address, { key: 'Enter' })
    expect(within(page).getByLabelText('Chọn ảnh 1 cho biến thể')).not.toBeChecked()
    expect(within(page).getByLabelText('Chọn ảnh 2 cho biến thể')).toBeChecked()
    expect(within(page).getByLabelText('Chọn ảnh 3 cho biến thể')).toBeChecked()
    expect(within(page).getByLabelText('Ảnh đại diện biến thể 2')).toBeChecked()
    fireEvent.click(within(page).getByRole('button', { name: 'Lưu thay đổi' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Xác nhận' }))
    await waitFor(() => expect(api.updateCatalogItem).toHaveBeenCalledWith('access-for-test', 'v2', expect.objectContaining({
      VariantImageUrls: ['https://demo.supabase.co/blue-front.png', 'https://cdn.example.test/blue-back.png'],
      DefaultImageUrl: 'https://demo.supabase.co/blue-front.png', IsDefaultVariant: false,
      AdditionalImages: [{ ImageUrl: 'https://demo.supabase.co/blue-front.png' }, { ImageUrl: 'https://cdn.example.test/blue-back.png' }],
    })))
  })

})
