import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, LoaderCircle, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { queryKeys } from '@/api/queryKeys'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { interviewsApi, ROUND_LABELS } from '@/features/interviews/api'
import { ReportView, ReviewTranscript } from '@/features/interviews/components/InterviewReport'
import { LiveRoom, PreJoin } from '@/features/interviews/components/InterviewRoom'
import { MockInterviewButton } from '@/features/interviews/components/MockInterviewButton'
import { useDeleteInterview, useInterview } from '@/features/interviews/hooks'

function Working({ text }) {
  return (
    <Card className="max-w-2xl">
      <CardContent className="flex items-center gap-3 py-6 text-sm">
        <LoaderCircle className="size-5 animate-spin text-primary" aria-hidden="true" />
        {text}
      </CardContent>
    </Card>
  )
}

export default function InterviewPage() {
  const { interviewId } = useParams()
  const query = useInterview(interviewId)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const remove = useDeleteInterview(interviewId)
  const [joined, setJoined] = useState(false)
  const interview = query.data

  const onEnded = async (_reason, needsFinish = false) => {
    if (needsFinish) {
      try {
        await interviewsApi.finish(interviewId)
      } catch {
        // already ended
      }
    }
    queryClient.invalidateQueries({ queryKey: queryKeys.interviews.all() })
    await queryClient.refetchQueries({ queryKey: queryKeys.interviews.detail(interviewId) })
    setJoined(false)
  }

  if (query.isPending) return <p className="text-muted-foreground">Loading…</p>
  if (query.isError) return <p className="text-destructive">{query.error.message}</p>

  const status = interview.status
  // A call that is running in another tab (or was cut off) can be rejoined.
  const inCall = joined || status === 'in_progress'

  let body
  if (status === 'planning')
    body = <Working text="Maya is preparing your questions from the job and your resume…" />
  else if (status === 'failed')
    body = (
      <Card className="max-w-2xl">
        <CardContent className="space-y-3 py-6 text-sm">
          <p role="alert" className="text-destructive">
            {interview.error ?? 'The interview could not be prepared.'}
          </p>
          <MockInterviewButton job={interview.job} variant="default" label="Try again" />
        </CardContent>
      </Card>
    )
  else if (status === 'ready' && !joined)
    body = <PreJoin interview={interview} onJoin={() => setJoined(true)} />
  else if (inCall) body = <LiveRoom interview={interview} onEnded={onEnded} autoStart={joined} />
  else if (status === 'ended') body = <ReviewTranscript interview={interview} />
  else if (status === 'reporting')
    body = <Working text="Writing your report — this takes about half a minute…" />
  else
    body = (
      <ReportView
        interview={interview}
        actions={
          <>
            <MockInterviewButton job={interview.job} retryOf={interview} />
            <MockInterviewButton job={interview.job} variant="outline" label="Practice again" />
          </>
        }
      />
    )

  return (
    <>
      <PageHeader
        title={`Mock interview — ${interview.job.title}`}
        description={`${interview.job.company} · ${ROUND_LABELS[interview.round] ?? interview.round} round · ${interview.minutes} minutes`}
        actions={
          <>
            <Button variant="ghost" onClick={() => navigate('/interviews')}>
              <ArrowLeft />
              All interviews
            </Button>
            <Link
              to={`/jobs/${interview.job.id}`}
              className="inline-flex h-9 items-center rounded-md px-3 text-sm hover:bg-accent"
            >
              Job details
            </Link>
            {!inCall && !['planning', 'reporting'].includes(status) && (
              <Button
                variant="ghost"
                aria-label="Delete interview"
                onClick={() =>
                  remove.mutate(undefined, { onSuccess: () => navigate('/interviews') })
                }
              >
                <Trash2 />
              </Button>
            )}
          </>
        }
      />
      {body}
    </>
  )
}
