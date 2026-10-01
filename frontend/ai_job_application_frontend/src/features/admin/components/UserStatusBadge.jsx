import { Badge } from '@/components/ui/badge'

import { userStatus } from '../userRules'

const STYLES = {
  pending: { variant: 'warning', label: 'Pending' },
  approved: { variant: 'success', label: 'Approved' },
  rejected: { variant: 'destructive', label: 'Rejected' },
  deactivated: { variant: 'outline', label: 'Deactivated' },
}

export function UserStatusBadge({ user }) {
  const style = STYLES[userStatus(user)]
  return <Badge variant={style.variant}>{style.label}</Badge>
}

export function RoleBadge({ role }) {
  return role === 'admin' ? <Badge variant="default">Admin</Badge> : null
}
