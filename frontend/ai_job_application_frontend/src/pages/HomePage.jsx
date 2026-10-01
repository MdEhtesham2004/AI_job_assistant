import { Settings, UserRound, Users } from 'lucide-react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const linkClass = 'inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline'

export default function HomePage() {
  const { user } = useAuth()
  const firstName = user?.full_name?.split(' ')[0]

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome, ${firstName}` : 'Welcome'}
        description="AI Job Application Platform — features are added phase by phase."
      />
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>Get started</CardTitle>
          <CardDescription>
            Complete your profile and check your settings. Resumes and jobs arrive in the next
            phases.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Link to="/profile" className={linkClass}>
            <UserRound className="size-4" aria-hidden="true" />
            Complete your profile
          </Link>
          <Link to="/settings" className={linkClass}>
            <Settings className="size-4" aria-hidden="true" />
            Review your settings
          </Link>
          {user?.role === 'admin' && (
            <Link to="/admin/users" className={linkClass}>
              <Users className="size-4" aria-hidden="true" />
              Approve pending sign-ups
            </Link>
          )}
        </CardContent>
      </Card>
    </>
  )
}
