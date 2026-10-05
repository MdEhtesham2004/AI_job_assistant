import { LoaderCircle, Mail, RefreshCw, Sparkles } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import { useDigest, useRunDigest } from '../api'

/** Dashboard: the best new matches (the daily digest), with "check now". */
export function DigestCard() {
  const digest = useDigest()
  const state = digest.data
  const run = useRunDigest(state?.running_task_id)
  const d = state?.digest

  let note = 'Your best new matches arrive here every morning.'
  if (d && !d.is_today) note = `Last digest: ${d.digest_date}.`
  if (d?.is_today) {
    note =
      d.jobs.length > 0
        ? `Today: ${d.new_jobs} new job${d.new_jobs === 1 ? '' : 's'}, ${d.scored} scored for you.`
        : `Today: ${d.new_jobs} new job${d.new_jobs === 1 ? '' : 's'}, none at or above your minimum score.`
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" aria-hidden="true" />
          Today&apos;s matches
        </CardTitle>
        <CardDescription>{note}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {d?.jobs?.length > 0 && (
          <ol className="space-y-2" aria-label="Best new matches">
            {d.jobs.map((job) => (
              <li key={job.job_id} className="flex items-start justify-between gap-3 text-sm">
                <span className="min-w-0">
                  <Link to={`/jobs/${job.job_id}`} className="font-medium hover:underline">
                    {job.title}
                  </Link>
                  <span className="block truncate text-xs text-muted-foreground">
                    {job.company}
                    {job.location ? ` · ${job.location}` : ''}
                  </span>
                </span>
                <span className="shrink-0 font-semibold tabular-nums">{job.score}</span>
              </li>
            ))}
          </ol>
        )}
        {d?.is_today && d.jobs.length > 0 && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Mail className="size-3.5" aria-hidden="true" />
            {d.emailed ? 'Also emailed to you.' : (d.email_error ?? 'Not emailed.')}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => run.start()} disabled={run.running}>
            {run.running ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
            {run.running ? 'Checking…' : 'Check for new matches now'}
          </Button>
          <Link to="/settings" className="text-xs text-muted-foreground hover:underline">
            Digest settings
          </Link>
        </div>
      </CardContent>
    </Card>
  )
}
