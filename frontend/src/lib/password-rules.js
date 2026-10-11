// Mirrors the backend password policy: 8+ characters, an uppercase letter, a digit and a symbol.
export function passwordRules(password) {
  return [
    { label: 'Ít nhất 8 ký tự', met: password.length >= 8 },
    { label: 'Có chữ hoa', met: /\p{Lu}/u.test(password) },
    { label: 'Có chữ số', met: /[0-9]/.test(password) },
    { label: 'Ký tự đặc biệt', met: /[^\p{L}\p{N}\s]/u.test(password) },
  ]
}
