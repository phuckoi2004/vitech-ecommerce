export function comparisonFixture(count = 2) {
  return { Version: 1, Products: Array.from({ length: count }, (_, i) => ({
    ProductId: `product-${i}`, ProductVariantId: `variant-${i}`, ProductName: `Laptop ${i + 1}`, VariantName: '16GB / 512GB',
    Brand: 'VIETECH', Category: 'Laptop', Slug: `laptop-${i + 1}`, ImageUrl: i === 0 ? 'javascript:alert(1)' : '/laptop.png',
    Price: '18000000', InStock: i !== 1, Score: .8, Completeness: .9,
    Strengths: ['RAM 16 GB'], Limitations: ['chưa có dữ liệu CPU'],
  })), Rows: [{ Key: 'ram', Label: 'RAM', Values: Array(count).fill('16 GB') },
    { Key: 'cpu', Label: 'CPU', Values: Array(count).fill('Chưa có dữ liệu') }],
  Needs: ['lập trình'], Differences: ['Giá bán khác nhau.'], Recommendation: 'Chưa đủ căn cứ để chọn một mẫu phù hợp hơn.',
  Caveats: ['Không cam kết thời lượng pin.'], AnalysisStatus: 'verified', SnapshotAt: '2026-10-28T08:00:00Z' }
}
