import { LoaderCircle } from 'lucide-react'

export function FullPageSpinner({ label = 'Loading…' }) {
  return (
    <div className="flex min-h-screen items-center justify-center gap-2 text-sm text-muted-foreground">
      <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
      <span role="status">{label}</span>
    </div>
  )
}
