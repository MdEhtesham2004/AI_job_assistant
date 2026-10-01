import { StatusBadge } from '@/components/common/StatusBadge'

export function ServiceRow({ name, status, statusLabel, detail }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <span className="font-medium">{name}</span>
      <span className="flex items-center gap-3">
        {detail && <span className="text-sm text-muted-foreground">{detail}</span>}
        <StatusBadge status={status} label={statusLabel} />
      </span>
    </li>
  )
}
