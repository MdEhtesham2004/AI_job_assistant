import { Badge } from '@/components/ui/badge'

import { APPROVAL, EMAIL_STATUS, VERIFICATION } from '../api'

export function VerificationBadge({ value }) {
  const style = VERIFICATION[value] ?? VERIFICATION.unverified
  return <Badge variant={style.variant}>{style.label}</Badge>
}

export function ApprovalBadge({ value }) {
  const style = APPROVAL[value] ?? APPROVAL.pending
  return <Badge variant={style.variant}>{style.label}</Badge>
}

export function EmailStatusBadge({ status }) {
  const style = EMAIL_STATUS[status] ?? EMAIL_STATUS.draft
  return <Badge variant={style.variant}>{style.label}</Badge>
}
