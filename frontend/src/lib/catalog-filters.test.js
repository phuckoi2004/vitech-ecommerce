import { describe, expect, test } from 'vitest'
import { findPriceRange, hasListingFilters, knownSpecs, newsAbout, readListing } from './catalog-filters.js'

describe('category listing state', () => {
  test('reads the URL with popular as the default sort and ignores malformed criteria', () => {
    const listing = readListing(new URLSearchParams('sort=bogus&stock=1&spec=chip:snapdragon&spec=chip:snapdragon&spec=broken'))
    expect(listing).toEqual({ brandId: '', price: '', sort: 'popular', inStock: true, newArrivals: false, specs: ['chip:snapdragon'] })
    expect(hasListingFilters(listing)).toBe(true)
    expect(hasListingFilters(readListing(new URLSearchParams('sort=price_asc')))).toBe(false)
  })

  test('keeps only options the category still offers', () => {
    const facets = [{ Key: 'chip', Options: [{ Value: 'snapdragon' }] }, { Key: 'ram', Options: [{ Value: '8gb' }] }]
    expect(knownSpecs(['chip:snapdragon', 'chip:old', 'ram:8gb', 'nope:8gb'], facets)).toEqual(['chip:snapdragon', 'ram:8gb'])
  })

  test("a category's own price range wins; the homepage menu's ranges still work", () => {
    const ranges = [{ Value: '2-4', Label: '2 – 4 triệu', MinPrice: '2000000.00', MaxPrice: '3999999.99' }]
    expect(findPriceRange('2-4', ranges)).toEqual({ value: '2-4', label: '2 – 4 triệu', minPrice: '2000000.00', maxPrice: '3999999.99' })
    expect(findPriceRange('from-20', ranges)).toMatchObject({ minPrice: '20000000' })
    expect(findPriceRange('nope', ranges)).toBeNull()
    expect(findPriceRange('', ranges)).toBeNull()
  })
})

describe('newsAbout', () => {
  const article = (Title, Summary = '') => ({ Title, Summary })

  test('matches the category name as a whole word, ignoring case', () => {
    const articles = [article('Loa Bluetooth đáng mua'), article('Các loại tai nghe'), article('Chọn ĐIỆN THOẠI pin trâu')]
    expect(newsAbout(articles, ['Loa'])).toEqual([articles[0]])
    expect(newsAbout(articles, ['Điện thoại pin trâu', 'Điện thoại'])).toEqual([articles[2]])
    expect(newsAbout(articles, ['Màn hình'])).toEqual([])
  })
})
