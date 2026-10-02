import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const STYLES = {
  queued: { variant: 'outline', label: 'Queued' },
  running: { variant: 'warning', label: 'Running' },
  succeeded: { variant: 'success', label: 'Done' },
  failed: { variant: 'destructive', label: 'Failed' },
  cancelled: { variant: 'outline', label: 'Cancelled' },
}

export function TaskStatusBadge({ status }) {
  const style = STYLES[status] ?? STYLES.queued
  return <Badge variant={style.variant}>{style.label}</Badge>
}

export function ProgressBar({ value, status }) {
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn(
          'h-full rounded-full transition-all',
          status === 'failed'
            ? 'bg-destructive'
            : status === 'succeeded'
              ? 'bg-success'
              : 'bg-primary',
        )}
        style={{ width: `${Math.max(value, status === 'running' ? 5 : 0)}%` }}
      />
    </div>
  )
}
