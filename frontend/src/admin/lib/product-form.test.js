import { expect, test } from 'vitest'
import { parseSpecifications, sharedForm, specificationsToHtml } from './product-form.js'

test('saved specifications open in the editor as one "Tên: Giá trị" line each and read back unchanged', () => {
  const saved = { RAM: '12GB', 'Chip xử lý': 'Exynos 2600', 'Kết nối': 'Wi-Fi <7> & "BT"' }
  const html = sharedForm({ Specifications: saved }).Specifications
  expect(html).toBe('<p>RAM: 12GB</p><p>Chip xử lý: Exynos 2600</p><p>Kết nối: Wi-Fi &lt;7&gt; &amp; &quot;BT&quot;</p>')
  expect(parseSpecifications(html)).toEqual(saved)
})

test('legacy non-text values become readable lines', () => {
  expect(specificationsToHtml({ GPS: true, Camera: ['50MP', '12MP'] })).toBe('<p>GPS: Có</p><p>Camera: 50MP, 12MP</p>')
  expect(specificationsToHtml(null)).toBe('')
})

test('formatting, list items, line breaks and typed bullets are lines; only the first colon separates the value', () => {
  const html = '<p><strong>Màn hình</strong>: 6.7&nbsp;inch<br>Thời gian: 10:30</p><ul><li><p>Pin: 5000 mAh</p></li></ul><p>• Sạc: 45W</p><p></p>'
  expect(parseSpecifications(html)).toEqual({ 'Màn hình': '6.7 inch', 'Thời gian': '10:30', Pin: '5000 mAh', Sạc: '45W' })
})

test('lines without a name and value, and names entered twice, are rejected with the line', () => {
  expect(() => parseSpecifications('<p>RAM: 12GB</p><p>Chống nước</p>')).toThrow('dòng “Chống nước” chưa đúng dạng Tên: Giá trị')
  expect(() => parseSpecifications('<p>RAM:</p>')).toThrow('dòng “RAM:”')
  expect(() => parseSpecifications('<p>RAM: 12GB</p><p>ram: 16GB</p>')).toThrow('“ram” được nhập hai lần')
})

test('an empty editor clears the specifications', () => {
  expect(parseSpecifications('')).toBeNull()
  expect(parseSpecifications('<p></p>')).toBeNull()
})
