import { Activity } from 'lucide-react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function HomePage() {
  return (
    <>
      <PageHeader
        title="Welcome"
        description="AI Job Application Platform — features are added phase by phase."
      />
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>Phase 2 — Project structure</CardTitle>
          <CardDescription>
            The backend and frontend skeletons are running. Sign-in, resumes and jobs arrive in the
            next phases.
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
