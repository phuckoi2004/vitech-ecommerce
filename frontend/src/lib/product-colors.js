// Small approximate colour indicators; product photos remain the reference for the finish.
// Match full names so "Xanh đen" cannot accidentally become plain black.
const PALETTE = {
  'đen': '#202124', 'đen classic': '#242424', 'đen không gian': '#292a2d', 'titan đen': '#353638',
  'trắng': '#faf9f6', 'trắng classic': '#f7f7f2', 'trắng mây': '#f3f2ee', 'trắng ngà': '#f3ead8',
  'bạc': '#c5c8cc', 'titan trắng': '#dadbd8', 'xám bạc': '#bec1c4', 'trắng/bạc': '#dedfdf',
  'xám': '#878b90', 'xám đen': '#595c62', 'xám sương mù': '#bfc5c8', 'xám lục': '#879b91',
  'titan tự nhiên': '#a8a39b', 'titan sa mạc': '#c8ac91', 'vàng sa mạc': '#cdb38b',
  'xanh dương': '#517dbb', 'xanh biển': '#407fbb', 'xanh lam khói': '#98b7c4',
  'xanh da trời': '#a8d2e4', 'xanh sky blue': '#b8d6e9', 'xanh blue sky': '#b8d6e9',
  'xanh cyan': '#79cbd9', 'băng thanh': '#bddbdf', 'xanh băng': '#c0dfed', 'xanh nhạt': '#add7e4',
  'xanh sáng': '#8acbdc', 'xanh đậm': '#253d65', 'xanh navy': '#263b60',
  'xanh indigo': '#525b95', 'xanh lưu ly': '#656ea4', 'đêm xanh thẳm': '#303b49',
  'xanh đen': '#293d48', 'xanh bóng đêm': '#354650', 'xanh chạng vạng': '#718b91',
  'xanh lá': '#719c73', 'xanh ngọc': '#7dbfbd', 'xanh ngọc bích': '#7da89e',
  'xanh mòng két': '#82a8a3', 'xanh mint': '#b3d8c4', 'xanh bạc hà': '#b3d8c4',
  'xanh lá xô thơm': '#a5b49a', 'xanh xô thơm': '#a5b49a', 'xanh quân đội': '#65745b',
  'squad xanh quân đội': '#65745b', 'tím': '#ad96bf', 'tím nhạt': '#d3c6df',
  'tím oải hương': '#c7b6d8', 'tím cobalt': '#55518b', 'tím bóng đêm': '#4e415a', 'tím đen': '#514a60',
  'hồng': '#e5b6c2', 'hồng phớt': '#efd1d3', 'hồng be': '#dbc5b9',
  'đỏ': '#c43741', 'đỏ burgundy': '#79323e', 'cam': '#e9a16c', 'cam vũ trụ': '#d78152',
  'cam đào hoàng hôn': '#efb69a', 'vàng': '#e3cb83', 'vàng nhạt': '#eee2b6',
  'vàng citrus': '#e7d97b', 'vàng chanh': '#d8df7e', 'vàng beige': '#d9c9ac',
  'vàng kem': '#e8ddbf', 'vàng trắng': '#e4dfcf', 'trắng vàng': '#e4dfcf', 'ánh sao': '#e7dfcf',
  'kem': '#e9dfc8', 'be': '#d6c4a8', 'nâu': '#8a6856', 'nâu cát trắng': '#b7a28d', 'sa thạch': '#c4b49d',
  'đen/bạc': 'linear-gradient(135deg, #252628 50%, #c6c9ce 50%)',
  'đen/vàng': 'linear-gradient(135deg, #252628 50%, #dbc681 50%)',
  'xám/trắng': 'linear-gradient(135deg, #93989d 50%, #f6f6f1 50%)',
  'hồng đen': 'linear-gradient(135deg, #e3abc1 50%, #252628 50%)',
  'blackpink': 'linear-gradient(135deg, #e3abc1 50%, #252628 50%)',
}

export function productColorSwatch(color) {
  const key = String(color ?? '').normalize('NFC').trim().toLocaleLowerCase('vi-VN').replace(/^màu\s+/, '')
  return PALETTE[key] ?? null
}
