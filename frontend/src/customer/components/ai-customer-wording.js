// Apply the current customer wording to saved AI answers without rewriting the conversation.
const replacements = [
  [/,?[ \t]*tối đa[ \t]+\d+[ \t]+lượt[ \t]*\/[ \t]*khách\b/gi, ''],
  [/Mình đã đối chiếu các phiên bản sau bằng dữ liệu hiện tại của VieTech:/gi, 'So sánh các mẫu sau:'],
  [/Chưa (?:thể chọn|đủ căn cứ để chọn|thể kết luận để chọn) một mẫu phù hợp hơn(?: với nhu cầu của bạn)?\.(?: Bạn cho mình biết nhu cầu ưu tiên nhé\.)?/gi, ''],
  [/Các mẫu có mức phù hợp gần nhau theo dữ liệu hiện có[;,] chưa đủ căn cứ chọn một mẫu vượt trội\./gi, 'Các mẫu có mức phù hợp gần nhau, chưa thể chọn một mẫu vượt trội.'],
  [/phù hợp hơn theo tiêu chí của VieTech nhờ/gi, 'phù hợp hơn với nhu cầu của bạn nhờ'],
  [/chưa đủ dữ liệu để xác nhận/gi, 'chưa thể xác nhận'],
  [/chưa đủ dữ liệu/gi, 'chưa rõ'],
  [/chưa có dữ liệu/gi, 'chưa rõ'],
  [/chỉ truyền dữ liệu|data only/gi, 'chỉ truyền tệp'],
  [/truyền dữ liệu/gi, 'truyền tệp'],
  [/dữ liệu đầu ra và đầu vào/gi, 'giới hạn đầu ra và đầu vào'],
  [/dữ liệu/gi, 'thông số'],
  [/có căn cứ xác nhận(?: trong điều kiện đã nêu)?/gi, 'đáp ứng trong điều kiện đã nêu'],
  [/có căn cứ về kết nối/gi, 'có thể kết nối'],
  [/đã có căn cứ ở/gi, 'được hỗ trợ ở'],
  [/có căn cứ qua/gi, 'qua'],
  [/chưa đủ căn cứ/gi, 'chưa thể kết luận'],
  [/đã xác minh/gi, ''],
  [/được xác minh/gi, 'phù hợp'],
  [/xác minh/gi, 'kiểm tra'],
  [/được đối chiếu với/gi, 'nằm trong'],
  [/đối chiếu/gi, 'kiểm tra'],
]

export function customerAiText(value) {
  let text = typeof value === 'string' ? value : ''
  for (const [pattern, replacement] of replacements) {
    text = text.replace(pattern, (match) => replacement && match[0] === match[0].toLocaleUpperCase('vi')
      ? replacement[0].toLocaleUpperCase('vi') + replacement.slice(1) : replacement)
  }
  return text.replace(/[;；]/g, ',').replace(/(\S)[ \t]{2,}(?=\S)/g, '$1 ').replace(/[ \t]+([,:.])/g, '$1').trim()
}
