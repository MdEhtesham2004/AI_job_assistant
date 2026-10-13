import { cn } from '@/lib/utils'

/** A flat sheet on the paper background: hairline edge, no shadow (Phase 21). */
export function Card({ className, ...props }) {
  return (
    <div className={cn('rounded-lg border bg-card text-card-foreground', className)} {...props} />
  )
}

export function CardHeader({ className, ...props }) {
  return <div className={cn('flex flex-col gap-1 p-5', className)} {...props} />
}

export function CardTitle({ className, ...props }) {
  return <h2 className={cn('text-[0.975rem] font-semibold leading-snug', className)} {...props} />
}

export function CardDescription({ className, ...props }) {
  return <p className={cn('max-w-prose text-sm text-muted-foreground', className)} {...props} />
}

export function CardContent({ className, ...props }) {
  return <div className={cn('px-5 pb-5', className)} {...props} />
}
