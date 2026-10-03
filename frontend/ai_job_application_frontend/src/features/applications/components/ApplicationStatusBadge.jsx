import { Badge } from '@/components/ui/badge'

import { STATUS_LABELS, STATUS_VARIANT } from '../api'

export function ApplicationStatusBadge({ status }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABELS[status] ?? status}</Badge>
}
