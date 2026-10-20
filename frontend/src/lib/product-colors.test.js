import { expect, test } from 'vitest'
import { productColorSwatch } from './product-colors.js'

test('colour names keep distinct finishes and support Vietnamese labels', () => {
  expect(productColorSwatch('Đen')).toBe('#202124')
  expect(productColorSwatch(' Màu xanh cyan ')).toBe('#79cbd9')
  expect(productColorSwatch('Trắng')).not.toBe(productColorSwatch('Đen'))
  expect(productColorSwatch('Xanh Blue Sky')).toBe(productColorSwatch('Xanh Sky Blue'))
  expect(productColorSwatch('Đen Không Gian')).not.toBe(productColorSwatch('Đêm xanh thẳm'))
  expect(productColorSwatch('Đen/Bạc')).toContain('linear-gradient')
})

test('an unknown name does not invent a colour', () => {
  expect(productColorSwatch('Tiêu chuẩn')).toBeNull()
  expect(productColorSwatch('Đặc biệt')).toBeNull()
  expect(productColorSwatch('Xanh')).toBeNull()
  expect(productColorSwatch(null)).toBeNull()
})
