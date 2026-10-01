import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const STATUS_STYLES = {
  healthy: { variant: 'success', dot: 'bg-success' },
  degraded: { variant: 'warning', dot: 'bg-warning' },
  unreachable: { variant: 'destructive', dot: 'bg-destructive' },
  checking: { variant: 'outline', dot: 'bg-muted-foreground animate-pulse' },
}

export function StatusBadge({ status, label }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.checking
  return (
    <Badge variant={style.variant}>
      <span className={cn('size-2 rounded-full', style.dot)} aria-hidden="true" />
      {label ?? status}
    </Badge>
  )
}
