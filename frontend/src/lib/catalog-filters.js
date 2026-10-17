// Upper limits end one cent before the next range, matching numeric(15, 2) prices.
export const PRICE_RANGES = [
  { value: 'under-5', label: 'Dưới 5 triệu', maxPrice: '4999999.99' },
  { value: '5-10', label: '5 – 10 triệu', minPrice: '5000000', maxPrice: '9999999.99' },
  { value: '10-15', label: '10 – 15 triệu', minPrice: '10000000', maxPrice: '14999999.99' },
  { value: '15-20', label: '15 – 20 triệu', minPrice: '15000000', maxPrice: '19999999.99' },
  { value: 'from-20', label: 'Từ 20 triệu', minPrice: '20000000' },
]
