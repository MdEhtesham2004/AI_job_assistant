import { ArrowLeft, ExternalLink, FileText, Mail } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { CHANNEL_LABELS, STATUS_LABELS } from '@/features/applications/api'
import { ApplicationStatusBadge } from '@/features/applications/components/ApplicationStatusBadge'
import { MoveButtons } from '@/features/applications/components/MoveButtons'
import { useApplication, useUpdateApplication } from '@/features/applications/hooks'
import { InterviewPrepCard } from '@/features/hunt/components/InterviewPrepCard'
import { MockInterviewButton } from '@/features/interviews/components/MockInterviewButton'
import { MatchScoreBadge } from '@/features/jobs/components/MatchScore'
import { ApplicationEmailCard } from '@/features/outreach/components/ApplicationEmailCard'
import { RepliesCard } from '@/features/outreach/components/RepliesCard'
import { KIND_LABELS } from '@/features/resumes/api'
import { formatDateTime } from '@/lib/format'

const SOURCE_LABELS = { user: 'you', system: 'system', email_reply: 'email reply' }
const EMAIL_STEPS = ['ready_to_apply', 'waiting_for_approval', 'approved', 'sending', 'failed']

export default function ApplicationDetailPage() {
  const { applicationId } = useParams()
  const query = useApplication(applicationId)
  const application = query.data

  return (
    <>
      <Link
        to="/applications"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All applications
      </Link>
      {query.isPending && <p className="text-muted-foreground">Loading…</p>}
      {query.isError && <p className="text-destructive">{query.error.message}</p>}
      {application && <Detail application={application} />}
    </>
  )
}

function Detail({ application }) {
  const { job } = application
  return (
    <>
      <PageHeader
        title={job.title}
        description={`${job.company}${job.location ? ` · ${job.location}` : ''}`}
        actions={
          <>
            <Link
              to={`/jobs/${job.id}`}
              className="inline-flex h-9 items-center gap-2 rounded-md border bg-card px-4 text-sm font-medium hover:bg-accent"
            >
              Job details
            </Link>
            <MockInterviewButton job={job} label="Practise the interview" />
            {job.apply_url && (
              <a
                href={job.apply_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 [&_svg]:size-4"
              >
                <ExternalLink aria-hidden="true" />
                Open apply link
              </a>
            )}
          </>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2 text-sm">
        <ApplicationStatusBadge status={application.status} />
        <span className="text-muted-foreground">{CHANNEL_LABELS[application.channel]}</span>
        <MatchScoreBadge score={application.match_score} />
        {application.applied_at && (
          <span className="text-muted-foreground">
            · applied {formatDateTime(application.applied_at)}
          </span>
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Next step</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {application.channel !== 'email' && application.status === 'ready_to_apply' && (
                <p className="text-sm text-muted-foreground">
                  Apply on the company&apos;s site with the link above, then click{' '}
                  <span className="font-medium">Mark as applied</span>.
                </p>
              )}
              {application.channel === 'email' && EMAIL_STEPS.includes(application.status) && (
                <p className="text-sm text-muted-foreground">
                  Write, review and approve the email below — it becomes{' '}
                  <span className="font-medium">Applied</span> when Gmail has sent it.
                </p>
              )}
              <MoveButtons application={application} />
              <NextAction application={application} />
            </CardContent>
          </Card>
          {['interview', 'in_process', 'offer'].includes(application.status) && (
            <InterviewPrepCard job={job} highlight={application.status === 'interview'} />
          )}
          <Card>
            <CardHeader>
              <CardTitle>Documents</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {application.resume ? (
                <a
                  href={application.resume.download_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-primary hover:underline"
                >
                  <FileText className="size-4" aria-hidden="true" />
                  Resume v{application.resume.version_no} ({KIND_LABELS[application.resume.kind]})
                </a>
              ) : (
                <p className="text-muted-foreground">No resume selected.</p>
              )}
              {application.cover_letter?.download_url ? (
                <a
                  href={application.cover_letter.download_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-primary hover:underline"
                >
                  <Mail className="size-4" aria-hidden="true" />
                  Cover letter ({application.cover_letter.status})
                </a>
              ) : (
                <p className="text-muted-foreground">No cover letter.</p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          {application.channel === 'email' && <ApplicationEmailCard application={application} />}
          {application.channel === 'email' && application.applied_at && (
            <RepliesCard applicationId={application.id} />
          )}
          <Timeline application={application} />
        </div>
      </div>
    </>
  )
}

function Timeline({ application }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="relative space-y-4 border-l pl-5">
          {[...application.history].reverse().map((entry) => (
            <li key={entry.id}>
              <span className="absolute -left-[5px] mt-1.5 size-2.5 rounded-full bg-primary" />
              <p className="text-sm">
                <span className="font-medium">{STATUS_LABELS[entry.to_status]}</span>
                {entry.from_status && (
                  <span className="text-muted-foreground">
                    {' '}
                    (from {STATUS_LABELS[entry.from_status]})
                  </span>
                )}
              </p>
              <p className="text-xs text-muted-foreground">
                {formatDateTime(entry.created_at)} · by {SOURCE_LABELS[entry.source]}
              </p>
              {entry.note && <p className="mt-1 text-sm">{entry.note}</p>}
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}

function NextAction({ application }) {
  const update = useUpdateApplication()
  const [value, setValue] = useState(application.next_action ?? '')
  const dirty = value !== (application.next_action ?? '')
  return (
    <form
      className="flex gap-2 border-t pt-4"
      onSubmit={(event) => {
        event.preventDefault()
        update.mutate({ id: application.id, changes: { next_action: value } })
      }}
    >
      <Input
        aria-label="Next action"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Your next action, e.g. Follow up on Friday"
      />
      <Button type="submit" variant="outline" disabled={!dirty || update.isPending}>
        Save
      </Button>
    </form>
  )
}
