const nameKey = (value) => String(value ?? '').normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/gi, 'd').toLowerCase().replace(/[\s_]+/g, '-')

const aliases = {
  phone: ['dien-thoai', 'phone', 'smartphone'], laptop: ['laptop', 'may-tinh-xach-tay'],
  tablet: ['may-tinh-bang', 'tablet'], headphones: ['tai-nghe', 'headphone', 'headphones'],
  speaker: ['loa', 'speaker', 'speakers'], keyboard: ['ban-phim', 'keyboard'], mouse: ['chuot', 'mouse'],
  monitor: ['man-hinh', 'monitor'], powerbank: ['pin-sac-du-phong', 'sac-du-phong', 'powerbank'],
  watch: ['dong-ho-thong-minh', 'smartwatch'], tv: ['tivi', 'tv'],
  desktop: ['may-tinh-de-ban', 'pc', 'desktop'], components: ['linh-kien-may-tinh', 'linh-kien', 'components'],
  accessories: ['phu-kien', 'accessories'], smartHome: ['gia-dung-thong-minh', 'smart-home', 'gia-dung'],
}

// Groups that share a showcase section, strongest first. Later entries only apply when an earlier partner is
// missing or already taken (no laptop: the phone goes with the tablet).
const SHOWCASE_PAIRS = [
  ['phone', 'laptop'], ['tablet', 'headphones'], ['keyboard', 'mouse'], ['desktop', 'components'],
  ['monitor', 'desktop'], ['speaker', 'headphones'], ['phone', 'tablet'], ['laptop', 'desktop'],
  ['monitor', 'components'], ['watch', 'phone'], ['speaker', 'tv'], ['powerbank', 'accessories'],
]

const matches = (item, group) => aliases[group].some((key) => key === nameKey(item.Slug) || key === nameKey(item.Name))

// Prefer the design's groups only when those categories exist; the rest retain their API display order.
export function selectHomeCategories(categories, preferred) {
  const selected = []
  for (const group of preferred) {
    const found = categories.find((item) => matches(item, group))
    if (found && !selected.includes(found)) selected.push(found)
  }
  return [...selected, ...categories.filter((item) => !selected.includes(item))]
}

// Every root category as showcase sections of one or two. Related categories share a section; one with no
// related partner left (or a group the list does not know) gets its own. Sections and tabs keep display order.
export function pairHomeCategories(categories) {
  const byGroup = new Map()
  for (const group of Object.keys(aliases)) {
    const found = categories.find((item) => matches(item, group))
    if (found) byGroup.set(group, found)
  }
  const partner = new Map()
  for (const [first, second] of SHOWCASE_PAIRS) {
    const a = byGroup.get(first)
    const b = byGroup.get(second)
    if (!a || !b || a === b || partner.has(a) || partner.has(b)) continue
    partner.set(a, b)
    partner.set(b, a)
  }
  const sections = []
  const placed = new Set()
  for (const item of categories) {
    if (placed.has(item)) continue
    const section = partner.has(item) ? [item, partner.get(item)] : [item]
    for (const entry of section) placed.add(entry)
    sections.push(section)
  }
  return sections
}
