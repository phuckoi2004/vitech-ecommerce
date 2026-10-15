import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import { returnListSearch } from '../lib/returns.js'
import useServiceRequestWorkflow from '../hooks/useServiceRequestWorkflow.js'
import { ReturnButton } from '../components/ReturnUi.jsx'
import ReturnInformation from '../components/ReturnInformation.jsx'
import ReturnRejectDialog from '../components/ReturnRejectDialog.jsx'
import ServiceRequestActions from '../components/ServiceRequestActions.jsx'

function ReturnWorkspace({ requestId }) {
  const [params] = useSearchParams(), navigate = useNavigate()
  const workflow = useServiceRequestWorkflow('return', requestId)
  const { item, detail, busy, auth } = workflow
  return <section aria-label="Chi tiết yêu cầu đổi trả" className="-my-1 flex min-w-0 flex-col gap-4 font-admin text-admin-text">
    <header className="flex min-h-[33px] items-center justify-between gap-4"><h2 className="m-0 text-xl leading-[normal] font-bold">{item ? 'Yêu cầu ' + item.RequestCode : 'Chi tiết yêu cầu đổi trả'}</h2><ReturnButton secondary className="text-admin-text!" disabled={busy} onClick={() => navigate('/admin/returns' + returnListSearch(params))}>← Danh sách đổi trả</ReturnButton></header>
    {!item && detail.loading ? <LoadingState label="Đang tải yêu cầu đổi trả…" /> : !item && detail.error ? <ErrorState message={detail.error} onRetry={workflow.refresh} /> : item && <>
      <ReturnInformation item={item} assignedName={item.AssignedStaffId === auth.user.UserId ? auth.user.FullName : null} />
      <ServiceRequestActions workflow={workflow} />
      {workflow.rejecting && <ReturnRejectDialog open busy={busy} error={workflow.error} onClose={workflow.closeReject} onSubmit={workflow.reject} />}
    </>}
  </section>
}
export default function ReturnDetailPage() {
  const { requestId } = useParams()
  return <ReturnWorkspace key={requestId} requestId={requestId} />
}
