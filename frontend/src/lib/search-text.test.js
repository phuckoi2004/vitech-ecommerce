import { expect, test } from 'vitest'
import { foldText, hasAllWords } from './search-text.js'

test('folds case, Vietnamese marks, đ and spaces like the backend', () => {
  expect(foldText('  Điện   THOẠI ')).toBe('dien thoai')
  expect(foldText('Đồng hồ Ưu đãi')).toBe('dong ho uu dai')
})

test('every typed word must be a whole word of the text', () => {
  expect(hasAllWords('Chọn điện thoại năm 2026', 'dien thoai')).toBe(true)
  expect(hasAllWords('Samsung Galaxy S26: có gì mới?', 'galaxy samsung')).toBe(true)
  expect(hasAllWords('Samsung Galaxy S26', 'samsung apple')).toBe(false)
  expect(hasAllWords('Bộ sạc chuẩn PD', 'pro')).toBe(false)
  expect(hasAllWords('Bất kỳ', '   ')).toBe(false)
})
