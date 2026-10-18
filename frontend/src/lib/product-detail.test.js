import { expect, test } from 'vitest'
import { initialVariant, variantImages, versionLabel } from './product-detail.js'

const blue = { ProductVariantId: 'blue', Price: '20000000', StockQuantity: 3 }
const black = { ProductVariantId: 'black', Price: '20000000', StockQuantity: 5 }

test('the product page opens on the default variant chosen in admin, not the first one listed', () => {
  expect(initialVariant([blue, black], 'black')).toBe(black)
})

test('a default variant that cannot be bought gives way to the first one that can', () => {
  expect(initialVariant([blue, { ...black, StockQuantity: 0 }], 'black')).toBe(blue)
  expect(initialVariant([{ ...blue, StockQuantity: 0 }, { ...black, StockQuantity: 0 }], 'black').ProductVariantId).toBe('black')
  expect(initialVariant([blue, black])).toBe(blue)
  expect(initialVariant([])).toBeNull()
})

test('variant photos respect the selected colour, including an explicitly empty selection', () => {
  const product = {
    Images: [{ ImageUrl: '/black.png', IsDefault: true, DisplayOrder: 0 }, { ImageUrl: '/blue.png', IsDefault: false, DisplayOrder: 1 }],
    VariantImages: { blue: [{ ImageUrl: '/blue-back.png', DisplayOrder: 2 }, { ImageUrl: '/blue.png', IsDefault: true, DisplayOrder: 1 }], empty: [] },
  }
  expect(variantImages(product, 'blue').map((image) => image.ImageUrl)).toEqual(['/blue.png', '/blue-back.png'])
  expect(variantImages(product, 'empty')).toEqual([])
  expect(variantImages({ Images: product.Images }, 'blue')).toHaveLength(2)
})

test('colours of a model without storage share one version instead of one version per colour', () => {
  expect(versionLabel({ VariantName: 'Đen', Color: 'Đen', Storage: null })).toBe('Tiêu chuẩn')
  expect(versionLabel({ VariantName: 'Bản Pro · Trắng', Color: 'Trắng', Storage: null })).toBe('Bản Pro')
  expect(versionLabel({ VariantName: 'Kèm bút', Color: null, Storage: null })).toBe('Kèm bút')
  expect(versionLabel({ VariantName: 'Đen · 256GB', Color: 'Đen', Storage: '256GB' })).toBe('256GB')
})
