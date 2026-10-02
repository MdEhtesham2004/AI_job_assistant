import { ChevronsDown, LoaderCircle } from 'lucide-react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import { describeQuery } from '../api'
import { isRunActive, useLoadMore, useSearchRun } from '../hooks'
import { RunStatusBadge } from './JobBadges'
import { JobRow } from './JobRow'

function summary(run) {
  const known = run.results_count - run.new_jobs_count
  const parts = [`${run.results_count} jobs`, `${run.new_jobs_count} just added`]
  if (known > 0) parts.push(`${known} already in your list`)
  return parts.join(' · ')
}

/** Every job one search returned (new and already known), with "Load more". */
export function SearchRunResults({ runId }) {
  const query = useSearchRun(runId)
  const loadMore = useLoadMore(runId)
  const run = query.data

  if (query.isPending) return <p className="text-sm text-muted-foreground">Loading…</p>
  if (query.isError) return <p className="text-sm text-destructive">{query.error.message}</p>

  const active = isRunActive(run)
  const firstLoad = active && run.jobs.length === 0

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{describeQuery(run.query)}</CardTitle>
          <RunStatusBadge status={run.status} />
        </div>
        <CardDescription>
          {firstLoad && 'Searching JSearch — this usually takes a few seconds.'}
          {run.jobs.length > 0 && summary(run)}
          {run.status === 'failed' && <span className="text-destructive"> {run.error}</span>}
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {firstLoad && (
          <div className="flex items-center gap-2 border-t px-5 py-6 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            Waiting for results…
          </div>
        )}
        {run.status === 'succeeded' && run.jobs.length === 0 && (
          <p className="border-t px-5 py-6 text-sm text-muted-foreground">
            No jobs matched. Try fewer keywords, another location or a longer date range.
          </p>
        )}
        {run.jobs.length > 0 && (
          <ul className="divide-y border-t">
            {run.jobs.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                label={
                  job.is_new ? (
                    <Badge variant="success">Just added</Badge>
                  ) : (
                    <Badge variant="outline">Already in your list</Badge>
                  )
                }
              />
            ))}
          </ul>
        )}
        {(run.jobs.length > 0 || run.can_load_more) && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t px-5 py-3 text-sm">
            <Link to="/jobs" className="font-medium text-primary hover:underline">
              See all your jobs
            </Link>
            {active && run.jobs.length > 0 && (
              <span className="flex items-center gap-2 text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                Loading more results…
              </span>
            )}
            {run.can_load_more && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadMore.mutate()}
                disabled={loadMore.isPending}
              >
                <ChevronsDown />
                Load more results
              </Button>
            )}
            {run.status === 'succeeded' && !run.can_load_more && run.jobs.length > 0 && (
              <span className="text-muted-foreground">No more results for this search.</span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
