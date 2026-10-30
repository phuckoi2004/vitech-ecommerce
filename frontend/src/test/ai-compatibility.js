export function compatibilityFixture(status = 'unknown') {
  return {
    Version: 1, RuleVersion: 'laptop-monitor-v1', CheckType: 'laptop_monitor', Status: status,
    Products: [
      { ProductId: 'laptop-id', ProductVariantId: 'laptop-sku', ProductName: 'ASUS Zenbook UX3405', Kind: 'laptop',
        VariantName: '16GB / 512GB', Slug: 'asus-zenbook', ImageUrl: '/laptop.png', InStock: true,
        Facts: ['HDMI output: 2.1'] },
      { ProductId: 'monitor-id', ProductVariantId: 'monitor-sku', ProductName: 'LG 27GR93U', Kind: 'monitor',
        VariantName: 'Tiêu chuẩn', Slug: 'lg-27', ImageUrl: null, InStock: true,
        Facts: ['HDMI input: 2.1', 'Tần số quét: 144Hz'] },
    ],
    Request: { Width: 3840, Height: 2160, RefreshHz: 144, SourceConnector: null, DirectOnly: false },
    Criteria: [
      { Id: 'connection', Label: 'Kết nối cơ bản', Status: 'compatible', Requested: true,
        Summary: 'Có đầu ra HDMI và đầu vào phù hợp đã xác minh; kết nối cơ bản cần cáp phù hợp.',
        Evidence: ['HDMI output: 2.1', 'HDMI input: 2.1'] },
      { Id: 'signal_mode', Label: 'Chế độ tín hiệu trên toàn bộ đường truyền', Status: 'unknown', Requested: true,
        Summary: 'Chưa đủ dữ liệu để xác nhận 3840×2160 ở 144Hz trên toàn bộ đường truyền.', Evidence: [] },
    ],
    Conditions: ['Cáp HDMI truyền video phù hợp giữa hai cổng đã xác minh.'],
    Missing: ['Chế độ tín hiệu đầu ra của laptop', 'Khả năng của cáp đang dùng, định dạng màu và điều kiện DSC'],
    Limitations: ['Kết quả theo thông số, không phải kết quả cắm thử thiết bị.'],
    Explanation: 'Có căn cứ về kết nối cơ bản qua HDMI. Chưa thể xác nhận đạt đầy đủ độ phân giải và tần số yêu cầu.',
    ExplanationSource: 'backend', AnalysisStatus: 'verified', SnapshotAt: '2026-10-28T08:00:00Z',
  }
}
