// @vitest-environment node
import { describe, expect, test } from 'vitest'
import { queryString } from '../../../services/api/client.js'
import { historyFilters, historyQuery, orderItemsText, reviewProducts } from './orderHistory.js'

const params = (text) => new URLSearchParams(text)

describe('order history filters', () => {
  test('the URL gives the filters; unknown tabs, malformed days and pages mean no filter', () => {
    expect(historyFilters(params('status=received&code=%20VT26%20&from=2026-01-01&to=2026-10-04&page=3')))
      .toEqual({ tab: 'received', code: 'VT26', from: '2026-01-01', to: '2026-10-04', page: 3 })
    expect(historyFilters(params('status=lost&from=01/01/2026&to=2026-1-4&page=-2')))
      .toEqual({ tab: '', code: '', from: '', to: '', page: 1 })
  })

  test('a tab asks for every status it groups and the days cover whole Vietnam days', () => {
    const query = historyQuery({ tab: 'processing', code: 'VT26', from: '2026-01-01', to: '2026-12-31', page: 2 })
    expect(query).toEqual({
      order_status: ['Confirmed', 'Processing'], order_code: 'VT26', ordered_from: '2026-01-01T00:00:00+07:00',
      ordered_to: '2027-01-01T00:00:00+07:00', page: 2, page_size: 10,
    })
    expect(queryString(query)).toBe('?order_status=Confirmed&order_status=Processing&order_code=VT26'
      + '&ordered_from=2026-01-01T00%3A00%3A00%2B07%3A00&ordered_to=2027-01-01T00%3A00%3A00%2B07%3A00&page=2&page_size=10')
    expect(queryString(historyQuery({ tab: '', code: '', from: '', to: '', page: 1 }))).toBe('?page=1&page_size=10')
  })
})

describe('order history cards', () => {
  const line = (ProductName, ProductSlug) => ({ ProductName, ProductSlug })

  test('the first product names the order and the other lines are counted', () => {
    expect(orderItemsText([line('iPhone 18 Pro Max')])).toBe('iPhone 18 Pro Max')
    expect(orderItemsText([line('iPhone 18 Pro Max'), line('Ốp lưng'), line('Sạc 30W')])).toBe('iPhone 18 Pro Max và 2 sản phẩm khác')
    expect(orderItemsText([])).toBe('')
  })

  test('a received order offers reviews once per product still to review that has a page', () => {
    const Items = [line('iPhone 18', 'iphone-18'), line('iPhone 18', 'iphone-18'), line('Ốp lưng', 'op-lung'), line('Đã xóa', null),
      { ...line('Sạc 30W', 'sac-30w'), ReviewId: 'r1' }]
    const products = [{ slug: 'iphone-18', name: 'iPhone 18' }, { slug: 'op-lung', name: 'Ốp lưng' }]
    expect(reviewProducts({ OrderStatus: 'Delivered', Items })).toEqual(products)
    expect(reviewProducts({ OrderStatus: 'Completed', Items })).toEqual(products)
    expect(reviewProducts({ OrderStatus: 'Shipping', Items })).toEqual([])
  })
})
