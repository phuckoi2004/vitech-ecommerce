import { describe, expect, test } from 'vitest'
import { pairHomeCategories } from './categories.js'

const category = (name, slug) => ({ CategoryId: slug, Name: name, Slug: slug })
const names = (sections) => sections.map((section) => section.map((item) => item.Name))

describe('pairHomeCategories', () => {
  test('shows every root category, pairing related ones and leaving the rest on their own', () => {
    const roots = [
      category('Điện thoại', 'dien-thoai'), category('Laptop', 'laptop'), category('Máy tính bảng', 'may-tinh-bang'),
      category('Tai nghe', 'tai-nghe'), category('Màn hình', 'man-hinh'), category('Bàn phím', 'ban-phim'),
      category('Chuột', 'chuot'), category('Loa', 'loa'), category('Pin sạc dự phòng', 'pin-sac-du-phong'),
    ]
    expect(names(pairHomeCategories(roots))).toEqual([
      ['Điện thoại', 'Laptop'], ['Máy tính bảng', 'Tai nghe'], ['Màn hình'], ['Bàn phím', 'Chuột'], ['Loa'],
      ['Pin sạc dự phòng'],
    ])
  })

  test('falls back to the next related partner and keeps display order inside a section', () => {
    const roots = [category('Loa', 'loa'), category('Máy tính bảng', 'may-tinh-bang'), category('Tai nghe', 'tai-nghe'),
      category('Điện thoại', 'dien-thoai')]
    expect(names(pairHomeCategories(roots))).toEqual([['Loa'], ['Máy tính bảng', 'Tai nghe'], ['Điện thoại']])
    expect(names(pairHomeCategories(roots.filter((item) => item.Slug !== 'may-tinh-bang'))))
      .toEqual([['Loa', 'Tai nghe'], ['Điện thoại']])
  })

  test('matches by name when the slug is custom and gives unknown categories their own section', () => {
    const roots = [category('Bàn phím', 'keyboard-co'), category('Máy in', 'may-in'), category('Chuột', 'chuot-gaming')]
    expect(names(pairHomeCategories(roots))).toEqual([['Bàn phím', 'Chuột'], ['Máy in']])
  })
})
