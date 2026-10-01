import { Activity } from 'lucide-react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

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
          <CardTitle>You are signed in</CardTitle>
          <CardDescription>
            Accounts and sign-in are ready. Profiles and user management arrive next, then resumes
            and jobs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link
            to="/system"
            className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
          >
            <Activity className="size-4" aria-hidden="true" />
            Open System Status
          </Link>
        </CardContent>
      </Card>
    </>
  )
}
