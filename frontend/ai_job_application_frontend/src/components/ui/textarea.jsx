import { cn } from '@/lib/utils'

export function Textarea({ className, ...props }) {
  return (
    <textarea
      className={cn(
        'flex min-h-20 w-full rounded-md border bg-card px-3 py-2 text-sm shadow-xs',
        'placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
      {...props}
    />
  )
}
