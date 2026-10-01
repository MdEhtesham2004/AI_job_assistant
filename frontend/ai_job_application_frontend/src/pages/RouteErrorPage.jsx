import { useRouteError } from 'react-router'

import { Button } from '@/components/ui/button'

export default function RouteErrorPage() {
  const error = useRouteError()
  console.error(error)

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        An unexpected error occurred while showing this page.
      </p>
      <Button onClick={() => window.location.reload()}>Reload</Button>
    </div>
  )
}
