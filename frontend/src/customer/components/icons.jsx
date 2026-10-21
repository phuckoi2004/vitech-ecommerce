// Line icons for the customer site (24×24, current color). Decorative: pair them with visible text or a label.

function Icon({ className = '', children }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
}

export const ArrowRightIcon = (props) => <Icon {...props}><path d="M5 12h14M13 6l6 6-6 6" /></Icon>
export const ChevronLeftIcon = (props) => <Icon {...props}><path d="m15 6-6 6 6 6" /></Icon>
export const ChevronRightIcon = (props) => <Icon {...props}><path d="m9 6 6 6-6 6" /></Icon>
export const ChevronDownIcon = (props) => <Icon {...props}><path d="m6 9 6 6 6-6" /></Icon>

const CATEGORY_SHAPES = {
  phone: <><rect x="7" y="2.75" width="10" height="18.5" rx="2.25" /><path d="M11 18h2" /></>,
  tablet: <><rect x="4.5" y="2.75" width="15" height="18.5" rx="2" /><path d="M11 18h2" /></>,
  laptop: <><rect x="4.5" y="5" width="15" height="10" rx="1.5" /><path d="M2.5 18.5h19" /></>,
  desktop: <><rect x="3" y="4" width="18" height="12" rx="1.5" /><path d="M9 20h6M12 16v4" /></>,
  chip: <><rect x="7" y="7" width="10" height="10" rx="1.5" /><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4" /></>,
  audio: <><path d="M4 15v-3a8 8 0 0 1 16 0v3" /><rect x="3" y="14" width="4" height="6" rx="1.5" /><rect x="17" y="14" width="4" height="6" rx="1.5" /></>,
  watch: <><rect x="6.5" y="6.5" width="11" height="11" rx="3" /><path d="m9 6.5.5-3.5h5l.5 3.5M9 17.5l.5 3.5h5l.5-3.5M12 9.5V12l1.5 1" /></>,
  accessory: <path d="M9 3v5M15 3v5M6.5 8h11v3a5.5 5.5 0 0 1-11 0zM12 16.5V21" />,
  other: <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></>,
}

// Category names are data, so the icon is picked from words in the name (first match wins, hence "máy tính"
// last: "Phụ kiện máy tính" is an accessory); anything else gets the grid icon.
const CATEGORY_WORDS = [
  ['phone', ['dien thoai', 'smartphone']],
  ['tablet', ['may tinh bang', 'tablet', 'ipad']],
  ['laptop', ['laptop', 'macbook']],
  ['chip', ['linh kien', 'cpu', 'ram', 'o cung']],
  ['accessory', ['phu kien', 'sac', 'cap']],
  ['audio', ['tai nghe', 'am thanh', 'loa']],
  ['watch', ['dong ho', 'smartwatch']],
  ['desktop', ['may tinh', 'pc', 'man hinh']],
]

// " dien thoai choi game ": no accents, whole words only, so "camera" does not match "ram".
function plainWords(text) {
  const plain = text.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/gi, 'd').toLowerCase()
  return ` ${plain.replace(/[^a-z0-9]+/g, ' ').trim()} `
}

export function CategoryIcon({ name = '', className = '' }) {
  const text = plainWords(name)
  const kind = CATEGORY_WORDS.find(([, words]) => words.some((word) => text.includes(` ${word} `)))?.[0] ?? 'other'
  return <Icon className={className}>{CATEGORY_SHAPES[kind]}</Icon>
}

export const TruckIcon = (props) => <Icon {...props}><path d="M3 6.5h11v9H3zM14 9.5h3.5L21 13v2.5h-7" /><circle cx="7" cy="17.5" r="1.75" /><circle cx="17" cy="17.5" r="1.75" /></Icon>
export const ReturnIcon = (props) => <Icon {...props}><path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.5M20 4v4.5h-4.5M20 12a8 8 0 0 1-13.7 5.6L4 15.5M4 20v-4.5h4.5" /></Icon>
export const ShieldIcon = (props) => <Icon {...props}><path d="M12 3 5 6v5.5c0 4.3 3 7.6 7 9.5 4-1.9 7-5.2 7-9.5V6z" /><path d="m9 12 2 2 4-4" /></Icon>
export const BadgeIcon = (props) => <Icon {...props}><circle cx="12" cy="9" r="5.5" /><path d="m9 14-1.5 7L12 19l4.5 2L15 14" /></Icon>
