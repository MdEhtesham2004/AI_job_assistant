import { Bot, CalendarClock, LoaderCircle, Play } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'
import { formatDateTime } from '@/lib/format'

import { useAutomation, useRunAutomation } from '../hooks'

const RUNNING = ['queued', 'running']

/**
 * Automations › Apply pipeline (Phase 20): prepares applications for jobs with an approved
 * contact — on click, or daily at the user's hour when switched on in Settings. Finding
 * recruiters is Scheduled searches' job.
 */
export function AutomationCard() {
  const status = useAutomation().data
  const run = useRunAutomation()
  if (!status) return null
  const last = status.last_run
  const running = RUNNING.includes(last?.status) || run.isPending
  const result = last?.status === 'succeeded' ? last.result : null
  const hour = `${String(status.hour).padStart(2, '0')}:00`

  return (
    <Card className="mb-4">
      <CardContent className="space-y-3 py-4 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="flex items-center gap-2 font-medium">
              <Bot className="size-4 text-primary" aria-hidden="true" />
              Prepare applications
            </p>
            <p className="text-xs text-muted-foreground">
              Scores the job, prepares the documents and drafts the email — at most{' '}
              {status.max_jobs} per run. Nothing is sent until you approve it in the{' '}
              <Link to="/outbox" className="text-primary hover:underline">
                Outbox
              </Link>
              .
            </p>
          </div>
          <Button
            size="sm"
            onClick={() => run.mutate()}
            disabled={!status.ready || status.saved_ready === 0 || running}
          >
            {running ? <LoaderCircle className="animate-spin" /> : <Play />}
            Prepare applications ({status.saved_ready})
          </Button>
        </div>

        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <CalendarClock className="size-3.5" aria-hidden="true" />
          {status.scheduled
            ? `Runs by itself every day at ${hour}.`
            : 'Runs only when you click.'}{' '}
          <Link to="/settings" className="text-primary hover:underline">
            Change in Settings
          </Link>
        </p>
        {!status.ready && (
          <p className="text-xs text-warning">
            {status.not_ready_reason}{' '}
            <Link to="/settings" className="text-primary hover:underline">
              Settings
            </Link>
          </p>
        )}
        {status.below_minimum > 0 && (
          <p className="text-xs text-muted-foreground">
            {status.below_minimum} job{status.below_minimum === 1 ? '' : 's'} with an approved
            contact scored below your minimum ({status.min_score}) and {"won't"} be prepared —{' '}
            <Link to="/settings" className="text-primary hover:underline">
              lower the minimum in Settings
            </Link>{' '}
            to include {status.below_minimum === 1 ? 'it' : 'them'}.
          </p>
        )}
        {status.ready && status.saved_ready === 0 && !status.below_minimum && (
          <p className="text-xs text-muted-foreground">
            No job is ready. A job is ready when it has an <b>approved contact</b> and no
            application yet —{' '}
            <Link to="/contacts" className="text-primary hover:underline">
              approve contacts
            </Link>{' '}
            (found by{' '}
            <Link to="/automations/searches" className="text-primary hover:underline">
              scheduled searches
            </Link>
            ).
          </p>
        )}

        {RUNNING.includes(last?.status) && (
          <ProgressBar value={last.progress} status={last.status} />
        )}
        {result && <LastRun result={result} finishedAt={last.finished_at} />}
        {last?.status === 'failed' && (
          <p role="alert" className="text-xs text-destructive">
            Last run failed: {last.error}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function LastRun({ result, finishedAt }) {
  return (
    <div className="space-y-1 rounded-md bg-muted/40 p-2 text-xs">
      <p className="text-muted-foreground">
        Last run {formatDateTime(finishedAt)}: {result.candidates} jobs with a contact ·{' '}
        {result.scored} scored
        {result.reused_scores ? ` (+${result.reused_scores} reused)` : ''} · {result.below_minimum}{' '}
        below your minimum ·{' '}
        <span className="font-medium text-foreground">{result.prepared} ready for approval</span>
      </p>
      {result.skipped?.slice(0, 3).map((reason) => (
        <p key={reason} className="text-muted-foreground">
          Skipped — {reason}
        </p>
      ))}
      {result.stopped && <p className="text-warning">Stopped: {result.stopped}</p>}
    </div>
  )
}
