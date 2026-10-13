import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileFunction } from 'node:vm'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transformWithOxc } from 'vite'

async function loadComponent(path, names, dependencies) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8').replace(/^import .+\r?\n/gm, '').replace(/export default function /g, 'function ').replace(/^export /gm, '')
  const { code } = await transformWithOxc(source, path, { jsx: { runtime: 'classic' } })
  return compileFunction(`const { ${Object.keys(dependencies).join(', ')} } = dependencies; ${code}; return { ${names.join(', ')} }`, ['dependencies'])(dependencies)
}

const table = await loadComponent('../components/DataTable.jsx', ['DataTable', 'DataError', 'formatMoney', 'ORDER_COLUMNS'], { React })
const settle = () => new Promise((resolve) => setImmediate(resolve))

function hooks() {
  const states = [], effects = [], pending = []
  let stateIndex = 0, effectIndex = 0, changed = false
  return {
    dependencies: {
      useState(initial) {
        const index = stateIndex++
        if (!(index in states)) states[index] = typeof initial === 'function' ? initial() : initial
        return [states[index], (next) => { states[index] = typeof next === 'function' ? next(states[index]) : next; changed = true }]
      },
      useEffect(callback, values) {
        const index = effectIndex++
        const previous = effects[index]
        if (!previous || values.some((value, offset) => value !== previous.values[offset])) {
          previous?.cleanup?.()
          const effect = { values }
          effects[index] = effect
          pending.push(() => { effect.cleanup = callback() })
        }
      },
    },
    render(callback) {
      let view
      do {
        changed = false
        stateIndex = effectIndex = 0
        view = callback()
        while (pending.length) pending.shift()()
      } while (changed)
      return view
    },
    unmount() { effects.forEach((effect) => effect.cleanup?.()) },
  }
}

function find(view, predicate) {
  if (!view || typeof view !== 'object') return null
  if (predicate(view)) return view
  for (const child of [view.props?.children].flat(Infinity)) {
    const result = find(child, predicate)
    if (result) return result
  }
  return null
}

async function dashboard(overrides = {}) {
  const hook = hooks()
  const selected = []
  const { DashboardPage } = await loadComponent('./DashboardPage.jsx', ['DashboardPage'], {
    React, ...hook.dependencies, ...table,
    currentMonth: () => '2026-10',
    getOrderStatistics: async () => ({ TotalOrders: 0, ByStatus: { Pending: 0 } }),
    getRevenueStatistics: async () => ({ NetRevenue: '0.00' }),
    getRecentOrders: async () => ({ Items: [], Total: 0 }),
    getLowStock: async () => ({ Items: [], Total: 0 }),
    ...overrides,
  })
  const auth = { withAccessToken: (call) => call('test-token') }
  return { render: () => hook.render(() => DashboardPage({ auth, onSelect: (id) => selected.push(id) })), selected, unmount: hook.unmount }
}

test('empty backend responses render four zero cards and both table headers without fixture records or removed widgets', async () => {
  const page = await dashboard()
  page.render()
  await settle()
  const view = page.render()
  const html = renderToStaticMarkup(view)
  assert.equal((html.match(/class="[^"]*\bdashboard-stat-value\b[^"]*">0(?: ₫)?<\/strong>/g) ?? []).length, 4)
  for (const label of ['Mã đơn', 'Người nhận', 'Giá trị', 'Trạng thái', 'Ngày đặt', 'Sản phẩm / Biến thể', 'Tồn kho', 'Chưa có đơn hàng.', 'Chưa có sản phẩm cần cảnh báo.']) assert.ok(html.includes(label), label)
  for (const removed of ['VT1028', 'Nguyễn Minh Anh', 'iPhone 17', 'Doanh thu theo tháng', 'Tìm kiếm trong quản trị', 'Notification']) assert.ok(!html.includes(removed), removed)
  find(view, (node) => node.type === 'button' && node.props.children === 'Xem tất cả').props.onClick()
  assert.deepEqual(page.selected, ['orders'])
  page.unmount()
})

test('one failed API leaves successful sections visible and exposes a retry action', async () => {
  let reads = 0
  const page = await dashboard({
    getRevenueStatistics: async () => { reads += 1; if (reads === 1) throw new Error('Lỗi kết nối doanh thu'); return { NetRevenue: '4500000.00' } },
    getOrderStatistics: async () => ({ TotalOrders: 7, ByStatus: { Pending: 2 } }),
  })
  page.render()
  await settle()
  const view = page.render()
  const html = renderToStaticMarkup(view)
  assert.ok(html.includes('>7</strong>'))
  assert.ok(html.includes('>2</strong>'))
  assert.ok(html.includes('Lỗi kết nối doanh thu'))
  assert.ok(html.includes('>—</strong>'))
  find(view, (node) => node.type === table.DataError).props.onRetry()
  page.render()
  await settle()
  assert.ok(renderToStaticMarkup(page.render()).includes('4.500.000 ₫'))
  page.unmount()
})

test('changing month aborts old reads and discards late results from the previous period', async () => {
  const calls = []
  const page = await dashboard({ getOrderStatistics: (token, month, signal) => new Promise((resolve) => { calls.push({ token, month, signal, resolve }) }) })
  const first = page.render()
  find(first, (node) => node.type === 'input' && node.props.type === 'month').props.onChange({ target: { value: '2026-09' } })
  page.render()
  assert.equal(calls[0].signal.aborted, true)
  assert.equal(calls[1].month, '2026-09')
  calls[1].resolve({ TotalOrders: 3, ByStatus: { Pending: 1 } })
  await settle()
  calls[0].resolve({ TotalOrders: 99, ByStatus: { Pending: 99 } })
  await settle()
  const html = renderToStaticMarkup(page.render())
  assert.ok(html.includes('>3</strong>'))
  assert.ok(!html.includes('>99</strong>'))
  page.unmount()
})

test('real order and stock rows preserve API statuses, zero stock and full inventory count', async () => {
  const page = await dashboard({
    getRecentOrders: async () => ({ Items: [{ OrderId: 'o1', OrderCode: 'VT-real', ReceiverName: 'Người nhận thật', TotalAmount: '1200000.00', OrderStatus: 'Shipping', OrderedAt: '2026-10-01T18:00:00Z' }], Total: 1 }),
    getLowStock: async () => ({ Items: [{ ProductVariantId: 'v1', ProductName: 'Sản phẩm thật', Sku: 'SKU-1', StockQuantity: 0 }], Total: 21 }),
  })
  page.render()
  await settle()
  const html = renderToStaticMarkup(page.render())
  for (const text of ['VT-real', 'Người nhận thật', '1.200.000 ₫', 'Đang giao', '02/10/2026', 'Sản phẩm thật', '>21</strong>', 'Xem tất cả (21)']) assert.ok(html.includes(text), text)
  page.unmount()
})

test('product sidebar opens and closes, supports nested navigation and exposes expanded state', async () => {
  const hook = hooks()
  const selected = []
  const { AdminLayout } = await loadComponent('../layouts/AdminLayout.jsx', ['AdminLayout'], { React, ...hook.dependencies, Icon: () => null })
  const props = { auth: { user: { Role: 'Admin', FullName: 'Admin' } }, title: 'Dashboard', breadcrumb: 'Trang chủ / Tổng quan', active: 'overview', menu: [{ id: 'catalog', label: 'Sản phẩm', children: [{ id: 'products', label: 'Danh sách sản phẩm' }] }], onSelect: (id) => selected.push(id) }
  const render = () => hook.render(() => AdminLayout(props))
  const groupButton = (view) => find(view, (node) => node.type === 'button' && node.props['aria-controls'] === 'admin-menu-catalog')
  assert.equal(groupButton(render()).props['aria-expanded'], false)
  groupButton(render()).props.onClick()
  assert.equal(groupButton(render()).props['aria-expanded'], true)
  find(render(), (node) => node.type === 'button' && node.props.children?.some((child) => child?.props?.children === 'Danh sách sản phẩm')).props.onClick()
  assert.deepEqual(selected, ['products'])
  groupButton(render()).props.onClick()
  assert.equal(groupButton(render()).props['aria-expanded'], false)
})
