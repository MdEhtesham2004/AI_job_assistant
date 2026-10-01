import { cn } from '@/lib/utils'

/** Native select styled like the other inputs. */
export function Select({ className, children, ...props }) {
  return (
    <select
      className={cn(
        'flex h-9 w-full rounded-md border bg-card px-3 py-1 text-sm shadow-xs',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
}
