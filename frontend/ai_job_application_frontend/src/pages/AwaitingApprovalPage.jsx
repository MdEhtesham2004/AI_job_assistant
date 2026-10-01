import { Hourglass } from 'lucide-react'
import { useState } from 'react'
import { Navigate } from 'react-router'
import { toast } from 'sonner'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function AwaitingApprovalPage() {
  const { user, reloadUser, logout } = useAuth()
  const [checking, setChecking] = useState(false)

  if (user?.approval_status === 'approved') return <Navigate to="/" replace />

  const checkAgain = async () => {
    setChecking(true)
    try {
      const fresh = await reloadUser()
      if (fresh.approval_status !== 'approved')
        toast.info('Your account is still waiting for approval.')
    } catch {
      toast.error('Could not check right now. Please try again.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <Card>
      <CardHeader className="items-center text-center">
        <div className="mb-2 flex size-12 items-center justify-center rounded-full bg-warning/15 text-warning">
          <Hourglass className="size-6" aria-hidden="true" />
        </div>
        <CardTitle className="text-xl">Awaiting approval</CardTitle>
        <CardDescription>
          Thanks, {user?.full_name}. Your account <strong>{user?.email}</strong> was created. An
          admin must approve it before you can continue.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <Button onClick={checkAgain} disabled={checking}>
          {checking ? 'Checking…' : 'Check again'}
        </Button>
        <Button variant="outline" onClick={logout}>
          Log out
        </Button>
      </CardContent>
    </Card>
  )
}
