import {
  ArrowLeft,
  Archive,
  Bookmark,
  BookmarkCheck,
  ClipboardPaste,
  ExternalLink,
  EyeOff,
  FileSearch,
  LoaderCircle,
  RotateCcw,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { PrepareApplicationCard } from '@/features/applications/components/PrepareApplicationCard'
import { AnalysisPanel } from '@/features/jobs/components/AnalysisPanel'
import { InterviewPrepCard } from '@/features/hunt/components/InterviewPrepCard'
import { ScreeningAnswersCard } from '@/features/hunt/components/ScreeningAnswersCard'
import { MockInterviewCard } from '@/features/interviews/components/MockInterviewCard'
import { DocumentsCard } from '@/features/jobs/components/DocumentsCard'
import { JobStateBadge, QualityBadge } from '@/features/jobs/components/JobBadges'
import { useFetchDescription, useJob, useUpdateJob } from '@/features/jobs/hooks'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'
import { formatDateTime, formatRelative } from '@/lib/format'

export default function JobDetailPage() {
  const { jobId } = useParams()
  const query = useJob(jobId)

  return (
    <>
      <Link
        to="/jobs"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All jobs
      </Link>
      {query.isPending && <p className="text-muted-foreground">Loading…</p>}
      {query.isError && <p className="text-destructive">{query.error.message}</p>}
      {query.data && <JobDetail job={query.data} />}
    </>
  )
}

function salary(job) {
  if (!job.salary_min && !job.salary_max) return null
  const format = (value) => Number(value).toLocaleString()
  const range = [job.salary_min, job.salary_max].filter(Boolean).map(format).join(' – ')
  return `${range}${job.salary_currency ? ` ${job.salary_currency}` : ''}`
}

function JobDetail({ job }) {
  const update = useUpdateJob(job.id)
  const [pasteOpen, setPasteOpen] = useState(false)
  const setState = (state) => update.mutate({ state })
  const hidden = job.state === 'skipped' || job.state === 'archived'
  const facts = [
    job.location,
    job.is_remote && 'Remote',
    job.employment_type,
    salary(job),
    job.posted_at && `Posted ${formatRelative(job.posted_at)}`,
  ].filter(Boolean)

  return (
    <>
      <PageHeader
        title={job.title}
        description={`${job.company}${job.company_domain ? ` · ${job.company_domain}` : ''}`}
        actions={
          <>
            {job.apply_url && (
              <a
                href={job.apply_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 [&_svg]:size-4"
              >
                <ExternalLink aria-hidden="true" />
                {/* A LinkedIn hiring post: you apply by email (Application card), not there. */}
                {job.source === 'linkedin_post' ? 'View post' : 'Apply'}
              </a>
            )}
            {hidden ? (
              <Button variant="outline" onClick={() => setState('new')}>
                <RotateCcw />
                Restore
              </Button>
            ) : (
              <>
                <Button
                  variant="outline"
                  onClick={() => setState(job.state === 'saved' ? 'new' : 'saved')}
                >
                  {job.state === 'saved' ? <BookmarkCheck /> : <Bookmark />}
                  {job.state === 'saved' ? 'Saved' : 'Save'}
                </Button>
                <Button variant="outline" onClick={() => setState('skipped')}>
                  <EyeOff />
                  Skip
                </Button>
                <Button variant="ghost" onClick={() => setState('archived')} aria-label="Archive">
                  <Archive />
                </Button>
              </>
            )}
          </>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <JobStateBadge state={job.state} />
        <QualityBadge quality={job.description_quality} />
        <span>{facts.join(' · ')}</span>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>Job description</CardTitle>
              <Button variant="outline" size="sm" onClick={() => setPasteOpen(true)}>
                <ClipboardPaste />
                {job.has_own_description ? 'Edit pasted description' : 'Paste description'}
              </Button>
            </div>
            {job.has_own_description && (
              <CardDescription>You pasted this description (only you see it).</CardDescription>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {job.description_quality !== 'complete' && <IncompleteNotice job={job} />}
            {job.description ? (
              <div className="whitespace-pre-line text-sm leading-relaxed">{job.description}</div>
            ) : (
              <p className="text-sm text-muted-foreground">No description available.</p>
            )}
          </CardContent>
        </Card>

        {/* Below xl the actions come first — a long post must not push them out of sight. */}
        <div className="order-first flex flex-col gap-6 xl:order-none">
          <PrepareApplicationCard job={job} />
          <AnalysisPanel job={job} />
          <InterviewPrepCard job={job} />
          <MockInterviewCard job={job} />
          <ScreeningAnswersCard job={job} />
          <DocumentsCard jobId={job.id} canGenerate={job.description_quality !== 'missing'} />
          <NotesCard job={job} />
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                <dt className="text-muted-foreground">Source</dt>
                <dd>{job.source === 'jsearch' ? 'JSearch' : job.source}</dd>
                <dt className="text-muted-foreground">Found by you</dt>
                <dd>{formatDateTime(job.first_found_at)}</dd>
                <dt className="text-muted-foreground">Last seen</dt>
                <dd>{formatDateTime(job.last_seen_at)}</dd>
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>

      {pasteOpen && <PasteDialog job={job} onClose={() => setPasteOpen(false)} />}
    </>
  )
}

function IncompleteNotice({ job }) {
  const running = job.active_tasks.find((t) => t.type === 'job_fetch_page')
  const fetch = useFetchDescription(job.id, running?.id)
  return (
    <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
      <p>
        {job.description_quality === 'missing'
          ? 'This job has no usable description.'
          : 'This description looks incomplete.'}{' '}
        Matching works best with the full text.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {job.apply_url && (
          <Button size="sm" variant="outline" onClick={fetch.start} disabled={fetch.running}>
            {fetch.running ? <LoaderCircle className="animate-spin" /> : <FileSearch />}
            Read it from the job page
          </Button>
        )}
        <span className="text-muted-foreground">or paste it yourself.</span>
      </div>
      {fetch.running && fetch.task && (
        <div className="mt-2">
          <ProgressBar value={fetch.task.progress} status={fetch.task.status} />
        </div>
      )}
      {fetch.task?.status === 'failed' && (
        <p role="alert" className="mt-2 text-destructive">
          {fetch.task.error}
        </p>
      )}
    </div>
  )
}

function NotesCard({ job }) {
  const update = useUpdateJob(job.id)
  const [notes, setNotes] = useState(job.notes ?? '')
  const dirty = notes !== (job.notes ?? '')
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your notes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Textarea
          aria-label="Notes"
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Referral, contact, impressions…"
        />
        <Button
          size="sm"
          disabled={!dirty || update.isPending}
          onClick={() => update.mutate({ notes })}
        >
          Save notes
        </Button>
      </CardContent>
    </Card>
  )
}

function PasteDialog({ job, onClose }) {
  const update = useUpdateJob(job.id)
  const [text, setText] = useState(job.has_own_description ? job.description : '')
  const save = (description) => update.mutate({ description }, { onSuccess: onClose })
  return (
    <Dialog
      open
      onClose={onClose}
      title="Paste the job description"
      description="Copy the full text from the job page. It is used for matching and only you see it."
      className="max-w-2xl"
    >
      <Textarea
        aria-label="Job description"
        rows={14}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="mt-4 flex justify-between gap-2">
        <div>
          {job.has_own_description && (
            <Button variant="ghost" onClick={() => save('')} disabled={update.isPending}>
              Remove my text
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => save(text)} disabled={update.isPending || text.trim().length < 50}>
            Save description
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
