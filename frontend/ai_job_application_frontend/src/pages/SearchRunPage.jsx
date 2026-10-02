import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { SearchRunResults } from '@/features/jobs/components/SearchRunResults'

export default function SearchRunPage() {
  const { runId } = useParams()
  return (
    <>
      <Link
        to="/jobs/search"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Find jobs
      </Link>
      <PageHeader title="Search results" />
      <SearchRunResults runId={runId} />
    </>
  )
}
