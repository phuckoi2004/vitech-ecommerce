import { useCallback, useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { useAdminLoad } from './useAdminQuery.js'
import { advanceReturn, getReturnDetail, rejectReturn } from '../services/returns.js'
import { advanceWarranty, getWarrantyDetail, rejectWarranty } from '../services/warranties.js'
import { warrantyStage, WARRANTY_RESULTS } from '../lib/warranties.js'

export default function useServiceRequestWorkflow(kind, id) {
  const auth = useInternalAuth(), warranty = kind === 'warranty'
  const load = useCallback((token, signal) => (warranty ? getWarrantyDetail : getReturnDetail)(token, id, signal), [warranty, id])
  const detail = useAdminLoad(load)
  const [saved, setSaved] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [rejecting, setRejecting] = useState(false), [notice, setNotice] = useState('')
  const [resultType, setResultType] = useState(''), [resultNote, setResultNote] = useState(''), [validation, setValidation] = useState('')
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const item = saved ?? detail.data
  const closed = Boolean(item && ['Completed', 'Rejected', 'Cancelled'].includes(item.Status))
  const canUpdate = auth.permissions.includes((warranty ? 'warranties' : 'returns') + ':update')
  const stage = item && warranty ? warrantyStage(item) : item?.Status
  async function write(call) {
    if (!canUpdate || closed || writing.current) return
    writing.current = true; setBusy(true); setError(''); setNotice('')
    try {
      const response = await auth.withAccessToken(call)
      if (mounted.current) { setSaved(response); setRejecting(false); setValidation(''); setNotice('Đã cập nhật phiếu.') }
    } catch (failure) {
      if (mounted.current) setError(failure.message)
    } finally {
      writing.current = false; if (mounted.current) setBusy(false)
    }
  }
  function advance() {
    if (!item || !canUpdate || closed || writing.current) return
    const resultRequired = warranty && stage === 'Repairing'
    if (resultRequired && (!WARRANTY_RESULTS.some(([key]) => key === resultType) || !resultNote.trim())) {
      setValidation('Vui lòng chọn kết quả bảo hành và nhập nội dung kết quả gửi cho khách.'); return
    }
    const body = { ExpectedStage: stage, ...(resultRequired ? { ResultType: resultType, ResultNote: resultNote.trim() } : {}) }
    void write((token) => warranty ? advanceWarranty(token, id, body) : advanceReturn(token, id, item.Status))
  }
  function reject(reason) {
    if (!reason.trim()) return
    void write((token) => (warranty ? rejectWarranty : rejectReturn)(token, id, reason.trim()))
  }
  function refresh() {
    if (writing.current) return
    setSaved(null); setError(''); setRejecting(false); setResultType(''); setResultNote(''); setValidation(''); detail.refresh()
  }
  return { auth, detail, item, closed, canUpdate, stage, busy, error, notice, rejecting, resultType, resultNote, validation, advance, reject, refresh,
    setResultType, setResultNote, chooseReject: () => { if (!writing.current) { setError(''); setRejecting(true) } },
    closeReject: () => { if (!writing.current) { setError(''); setRejecting(false) } }, clearError: () => { if (!writing.current) setError('') } }
}
