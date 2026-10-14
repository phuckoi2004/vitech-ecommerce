import { useCallback, useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { getAdminData } from '../../services/api/admin.js'
import useAdminQuery, { useAdminLoad } from './useAdminQuery.js'
import { getPurchaseVariants, purchaseReadBatch } from '../services/purchases.js'
import { getSupplierDirectory } from '../services/suppliers.js'

export default function usePurchaseDetail(purchaseId, editing, initialNotice = '') {
  const auth = useInternalAuth()
  const can = (action) => auth.permissions.includes('purchases:' + action)
  const path = '/admin/purchase-orders/' + encodeURIComponent(purchaseId)
  const detail = useAdminQuery(path, {}, can('view'))
  const [saved, setSaved] = useState(null)
  const po = saved ?? detail.data
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(initialNotice)
  const mounted = useRef(true), writing = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  const suppliers = useAdminLoad(getSupplierDirectory, can('view') && auth.permissions.includes('suppliers:view'))
  const productAccess = can('view') && auth.permissions.includes('products:view')
  const ids = JSON.stringify([...new Set(po?.Items.map((item) => item.ProductVariantId) ?? [])])
  const loadItems = useCallback(async (token, signal) => {
    const variants = await purchaseReadBatch(JSON.parse(ids), (id) => getAdminData(token, '/admin/variants/' + encodeURIComponent(id), {}, signal), signal)
    const products = await purchaseReadBatch([...new Set(variants.map((variant) => variant.ProductId))], (id) => getAdminData(token, '/admin/products/' + encodeURIComponent(id), {}, signal), signal)
    const names = new Map(products.map((product) => [product.ProductId, product.Name]))
    return variants.map((variant) => ({ ...variant, Name: names.get(variant.ProductId) }))
  }, [ids])
  // Individual reads include historical/hidden variants, unlike the current catalog list.
  const items = useAdminLoad(loadItems, productAccess && ids !== '[]')
  const catalog = useAdminLoad(getPurchaseVariants, productAccess && editing && can('update'))
  const variants = {
    data: [...new Map([...(catalog.data ?? []), ...(items.data ?? [])].map((variant) => [variant.ProductVariantId, variant])).values()],
    loading: items.loading || catalog.loading, error: items.error || catalog.error,
    refresh: () => { items.refresh(); catalog.refresh() },
  }
  const userIds = JSON.stringify([...new Set([po?.CreatedByName ? null : po?.CreatedByUserId, po?.DecidedByUserId, po?.ClosedByUserId].filter((id) => id && id !== auth.user.UserId))])
  const loadNames = useCallback(async (token, signal) => {
    const ids = JSON.parse(userIds)
    const users = await purchaseReadBatch(ids, (id) => getAdminData(token, '/admin/users/' + encodeURIComponent(id), { include_deleted: true }, signal), signal, true)
    return Object.fromEntries(ids.map((id, index) => [id, users[index]?.FullName]))
  }, [userIds])
  const users = useAdminLoad(loadNames, can('view') && auth.user.Role === 'Admin' && auth.permissions.includes('users:read') && auth.permissions.includes('users:manage') && userIds !== '[]')
  const names = { ...users.data, ...(po?.CreatedByName ? { [po.CreatedByUserId]: po.CreatedByName } : {}), [auth.user.UserId]: auth.user.FullName }
  const showHistory = Boolean(po?.Items.some((item) => item.ReceivedQuantity > 0) || ['Receiving', 'Completed', 'Closed'].includes(po?.Status))
  const receipts = useAdminQuery(path + '/receipts', {}, can('view') && showHistory && auth.permissions.includes('purchase_history:view'))

  function refresh(message, fresh) {
    if (message) setNotice(message)
    if (fresh?.PurchaseOrderId) setSaved(fresh)
    detail.refresh(); items.refresh(); catalog.refresh(); receipts.refresh()
  }
  async function run(call, permission, message) {
    if (!can(permission) || writing.current) return null
    writing.current = true; setBusy(true); setError(''); setNotice('')
    try {
      const result = await auth.withAccessToken(call)
      if (!mounted.current) return null
      if (result?.PurchaseOrderId) setSaved(result)
      if (message) setNotice(message)
      receipts.refresh()
      return result
    } catch (failure) { if (mounted.current) setError(failure.message); return null }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  return { auth, can, detail, po, suppliers, variants, users, names, receipts, showHistory, busy, error, notice, setError, run, refresh }
}
