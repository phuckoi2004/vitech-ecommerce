import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileFunction } from 'node:vm'
import { transformWithOxc } from 'vite'
import { AVATAR_TYPES } from '../../lib/account-api.js'

// Render the production profile component with isolated React hooks and API.
// Vite compiles the actual JSX; no DOM or additional test dependency is needed.
const source = readFileSync(new URL('./AccountPage.jsx', import.meta.url), 'utf8')
  .replace(/^import .+\r?\n/gm, '')
  .replace('export default function AccountPage()', 'function AccountPage()')
const { code } = await transformWithOxc(source, 'AccountPage.jsx', { jsx: { runtime: 'classic' } })
const loadProfile = compileFunction(`
  const { React, useEffect, useRef, useState, getDefaultAddress, AVATAR_TYPES } = dependencies
  ${code}
  return ProfileSection
`, ['dependencies'])

function deferred() {
  let resolve, reject
  const promise = new Promise((accept, decline) => { resolve = accept; reject = decline })
  return { promise, resolve, reject }
}

function harness(readAddress) {
  const states = [], refs = [], effects = []
  let stateIndex = 0, refIndex = 0, effectIndex = 0, changed = false
  const pendingEffects = []
  const Profile = loadProfile({
    React: { createElement: (type, props, ...children) => ({ type, props: { ...props, children } }) },
    useState(initial) {
      const index = stateIndex++
      if (!(index in states)) states[index] = typeof initial === 'function' ? initial() : initial
      return [states[index], (next) => {
        states[index] = typeof next === 'function' ? next(states[index]) : next
        changed = true
      }]
    },
    useRef(initial) {
      const index = refIndex++
      if (!(index in refs)) refs[index] = { current: initial }
      return refs[index]
    },
    useEffect(callback, dependencies) {
      const index = effectIndex++
      const previous = effects[index]
      if (!previous || dependencies.some((value, offset) => value !== previous.dependencies[offset])) {
        previous?.cleanup?.()
        const effect = { dependencies }
        effects[index] = effect
        pendingEffects.push(() => { effect.cleanup = callback() })
      }
    },
    getDefaultAddress: readAddress,
    AVATAR_TYPES,
  })
  const session = {
    user: { FullName: 'Khách hàng', PhoneNumber: '0912345678', Email: 'customer@example.com' },
    withAccessToken: (call) => call('access-token-for-test'),
    updateUser: () => {},
  }
  return {
    render() {
      let view
      do {
        changed = false
        stateIndex = refIndex = effectIndex = 0
        view = Profile({ session, onLeave: () => {} })
      } while (changed)
      for (const run of pendingEffects.splice(0)) run()
      return view
    },
  }
}

function find(view, predicate) {
  if (!view || typeof view !== 'object') return null
  if (predicate(view)) return view
  for (const child of view.props?.children ?? []) {
    if (Array.isArray(child)) {
      for (const nested of child) {
        const found = find(nested, predicate)
        if (found) return found
      }
    } else {
      const found = find(child, predicate)
      if (found) return found
    }
  }
  return null
}

async function settle() {
  // Let the component's then/catch callbacks update its isolated state.
  await Promise.resolve()
  await Promise.resolve()
}

test('failed address loading blocks the editable profile and retry restores the saved address', async () => {
  const failed = deferred(), retried = deferred()
  let reads = 0
  const profile = harness(() => (++reads === 1 ? failed.promise : retried.promise))
  assert.ok(find(profile.render(), (node) => node.props?.role === 'status'))
  failed.reject(new Error('Không tải được địa chỉ đã lưu.'))
  await settle()
  let view = profile.render()
  assert.equal(find(view, (node) => node.props?.role === 'alert').props.children[0], 'Không tải được địa chỉ đã lưu.')
  assert.equal(find(view, (node) => node.type === 'form'), null)
  const retry = find(view, (node) => node.type === 'button' && node.props.children[0] === 'Thử lại')
  retry.props.onClick()
  view = profile.render()
  assert.ok(find(view, (node) => node.props?.role === 'status'))
  assert.equal(reads, 2)
  retried.resolve({ Province: 'Hà Nội', Ward: 'Hoàn Kiếm', DetailAddress: '12 Hàng Bài' })
  await settle()
  view = profile.render()
  assert.equal(find(view, (node) => node.props?.role === 'alert'), null)
  assert.ok(find(view, (node) => node.type === 'form'))
  assert.equal(find(view, (node) => node.props?.id === 'cacc-province' && node.type === 'input').props.value, 'Hà Nội')
  assert.equal(find(view, (node) => node.props?.id === 'cacc-detail' && node.type === 'input').props.value, '12 Hàng Bài')
})

test('a successful null address opens the profile with empty address fields', async () => {
  const profile = harness(async () => null)
  profile.render()
  await settle()
  const view = profile.render()
  assert.equal(find(view, (node) => node.props?.role === 'alert'), null)
  assert.ok(find(view, (node) => node.type === 'form'))
  assert.equal(find(view, (node) => node.props?.id === 'cacc-name' && node.type === 'input').props.value, 'Khách hàng')
  for (const id of ['cacc-province', 'cacc-ward', 'cacc-detail']) {
    assert.equal(find(view, (node) => node.props?.id === id && node.type === 'input').props.value, '')
  }
})
