// @vitest-environment node
import { expect, test } from 'vitest'
import { filterReviews, reviewFilters, reviewImageUrl, reviewTimestamp } from './reviews.js'

const now = new Date('2026-10-13T17:30:00Z') // 14/10 in Vietnam.
const rows = [
  { ReviewId: 'today', Rating: 5, CreatedAt: '2026-10-13T17:05:00Z' },
  { ReviewId: 'week', Rating: 4, CreatedAt: '2026-10-07T17:00:00Z' },
  { ReviewId: 'outside', Rating: 5, CreatedAt: '2026-10-07T16:59:59Z' },
  { ReviewId: 'month', Rating: 3, CreatedAt: '2026-09-30T17:00:00Z' },
  { ReviewId: 'future', Rating: 5, CreatedAt: '2026-10-14T17:00:00Z' },
]
test('relative filters use inclusive Vietnam calendar boundaries and exclude future dates', () => {
  expect(filterReviews(rows, { period: 'today', rating: '' }, now).map((row) => row.ReviewId)).toEqual(['today'])
  expect(filterReviews(rows, { period: '7days', rating: '' }, now).map((row) => row.ReviewId)).toEqual(['today', 'week'])
  expect(filterReviews(rows, { period: 'month', rating: '5' }, now).map((row) => row.ReviewId)).toEqual(['today', 'outside'])
  expect(filterReviews(rows, { period: '', rating: '' }, now)).toEqual(rows)
})
test('a 30-day range crosses month boundaries using calendar dates', () => {
  const rows = [{ CreatedAt: '2026-09-14T17:00:00Z', Rating: 1 }, { CreatedAt: '2026-09-14T16:59:59Z', Rating: 1 }]
  expect(filterReviews(rows, { period: '30days' }, now)).toEqual([rows[0]])
})
test('invalid URL filters fall back safely and timestamps match the design in Vietnam time', () => {
  expect(reviewFilters(new URLSearchParams('period=bad&rating=99&page=-2'))).toEqual({ period: '', rating: '', page: 1 })
  expect(reviewTimestamp('2026-10-13T17:30:00Z')).toBe('14/10/2026 00:30')
  expect(reviewTimestamp(null)).toBe('—')
})
test('review image links allow actual HTTP assets and reject script URLs', () => {
  expect(reviewImageUrl('https://storage.example.com/review.jpg')).toBe('https://storage.example.com/review.jpg')
  expect(reviewImageUrl('/images/review.jpg')).toBe('/images/review.jpg')
  for (const url of ['javascript:alert(1)', '//other.example.com', 'data:text/html,test', null]) expect(reviewImageUrl(url)).toBeNull()
})
