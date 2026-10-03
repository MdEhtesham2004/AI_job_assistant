import { Bot, DownloadCloud, LoaderCircle, Lock, Play } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { useAuth } from '@/auth/useAuth'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'
import { formatDateTime } from '@/lib/format'

import { useAutomation, useRunAutomation } from '../hooks'

const RUNNING = ['queued', 'running']

/**
 * Outbox: automation runs only when you click.
 * 1. "Automate saved jobs" — jobs you already have with an approved contact (no new search).
 * 2. "Fetch new jobs & automate" — searches LinkedIn first (Apify credit); locked until an
 *    admin enables it in Settings › Platform.
 */
export function AutomationCard() {
  const status = useAutomation().data
  const run = useRunAutomation()
  const { user } = useAuth()
  const [confirmFetch, setConfirmFetch] = useState(false)
  if (!status) return null
  const last = status.last_run
  const running = RUNNING.includes(last?.status) || run.isPending
  const result = last?.status === 'succeeded' ? last.result : null
  const canFetch = status.ready && status.fetch_allowed && !status.fetch_problem && !running

  return (
    <Card className="mb-4">
      <CardContent className="space-y-3 py-4 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="flex items-center gap-2 font-medium">
              <Bot className="size-4 text-primary" aria-hidden="true" />
              Automation
            </p>
            <p className="text-xs text-muted-foreground">
              Scores the job, prepares the documents and drafts the email — at most{' '}
              {status.max_jobs} per run. Nothing is sent until you approve it below.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() => run.mutate('saved')}
              disabled={!status.ready || status.saved_ready === 0 || running}
            >
              {running ? <LoaderCircle className="animate-spin" /> : <Play />}
              Automate saved jobs ({status.saved_ready})
            </Button>
            <Button
              size="sm"
              variant={status.saved_ready === 0 ? 'default' : 'outline'}
              onClick={() => setConfirmFetch(true)}
              disabled={!canFetch}
              title={
                status.fetch_allowed ? undefined : 'Locked — an admin can enable it in Settings'
              }
            >
              {status.fetch_allowed ? <DownloadCloud /> : <Lock />}
              Fetch new jobs &amp; automate
            </Button>
          </div>
        </div>

        {!status.ready && (
          <p className="text-xs text-warning">
            {status.not_ready_reason}{' '}
            <Link to="/settings" className="text-primary hover:underline">
              Settings
            </Link>
          </p>
        )}
        {status.ready && status.saved_ready === 0 && (
          <p className="text-xs text-muted-foreground">
            No saved job is ready. A job is ready when it has an <b>approved contact</b> and no
            application yet —{' '}
            <Link to="/contacts" className="text-primary hover:underline">
              approve contacts
            </Link>
            {status.fetch_allowed ? ', or fetch new jobs.' : '.'}
          </p>
        )}
        {!status.fetch_allowed && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Lock className="size-3" aria-hidden="true" />
            Fetching new jobs uses paid API credit and is locked
            {user?.role === 'admin' ? (
              <>
                {' '}
                —{' '}
                <Link to="/settings" className="text-primary hover:underline">
                  enable it in Settings › Platform
                </Link>
              </>
            ) : (
              ' by your admin'
            )}
            .
          </p>
        )}
        {status.fetch_allowed && status.fetch_problem && (
          <p className="text-xs text-muted-foreground">
            To fetch: {status.fetch_problem}{' '}
            <Link to="/settings" className="text-primary hover:underline">
              Settings
            </Link>
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

      <Dialog
        open={confirmFetch}
        onClose={() => setConfirmFetch(false)}
        title="Fetch new jobs and automate?"
        description="This searches LinkedIn hiring posts (uses Apify credit), then scores and prepares the new jobs. New contacts are shown for your approval with each email."
      >
        <p className="mb-4 text-sm">
          Keywords: <span className="font-medium">{status.keywords.join(', ') || '—'}</span>
        </p>
        <div className="flex gap-2">
          <Button
            onClick={() => {
              run.mutate('fetch')
              setConfirmFetch(false)
            }}
          >
            Fetch &amp; automate
          </Button>
          <Button variant="outline" onClick={() => setConfirmFetch(false)}>
            Cancel
          </Button>
        </div>
      </Dialog>
    </Card>
  )
}

function LastRun({ result, finishedAt }) {
  const fetched = result.mode === 'fetch'
  return (
    <div className="space-y-1 rounded-md bg-muted/40 p-2 text-xs">
      <p className="text-muted-foreground">
        Last run ({fetched ? 'fetch & automate' : 'saved jobs'}) {formatDateTime(finishedAt)}:{' '}
        {fetched && `${result.posts} posts · `}
        {result.candidates} jobs with a contact · {result.scored} scored
        {result.reused_scores ? ` (+${result.reused_scores} reused)` : ''} · {result.below_minimum}{' '}
        below your minimum ·{' '}
        <span className="font-medium text-foreground">{result.prepared} ready for approval</span>
      </p>
      {result.empty_keywords?.length > 0 && (
        <p className="text-warning">
          No LinkedIn posts for “{result.empty_keywords.join('”, “')}”. Try a shorter keyword (e.g.
          “Data Scientist”) or a longer period in Settings.
        </p>
      )}
      {result.skipped?.slice(0, 3).map((reason) => (
        <p key={reason} className="text-muted-foreground">
          Skipped — {reason}
        </p>
      ))}
      {result.stopped && <p className="text-warning">Stopped: {result.stopped}</p>}
    </div>
  )
}
