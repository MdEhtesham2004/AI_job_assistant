import { FileText, LoaderCircle, Mail, PenLine } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'
import { formatDateTime } from '@/lib/format'

import { jobsApi } from '../api'
import { useGenerateDocument, useJobDocuments } from '../hooks'

const linkClass =
  'inline-flex h-8 items-center gap-1.5 rounded-md border bg-card px-3 text-sm font-medium hover:bg-accent [&_svg]:size-4'

function TaskLine({ action }) {
  if (action.running && action.task) {
    return <ProgressBar value={action.task.progress} status={action.task.status} />
  }
  if (action.task?.status === 'failed') {
    return (
      <p role="alert" className="text-xs text-destructive">
        {action.task.error}
      </p>
    )
  }
  return null
}

/** Tailored resume + cover letter for this job (Phase 10). */
export function DocumentsCard({ jobId, canGenerate }) {
  const docs = useJobDocuments(jobId)
  const [contact, setContact] = useState('')
  const running = (type) => docs.data?.active_tasks.find((t) => t.type === type)?.id
  const tailor = useGenerateDocument(() => jobsApi.tailor(jobId), {
    runningTaskId: running('resume_tailor'),
    label: 'Tailored resume',
  })
  const letter = useGenerateDocument(() => jobsApi.coverLetter(jobId, contact), {
    runningTaskId: running('cover_letter'),
    label: 'Cover letter',
  })
  const data = docs.data
  const noResume = data && !data.source

  return (
    <Card>
      <CardHeader>
        <CardTitle>Application documents</CardTitle>
        <CardDescription>
          Made from your resume — nothing is invented (checked by code). ≈ $0.002 each.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {noResume && (
          <p className="text-sm text-muted-foreground">
            <Link to="/resumes" className="text-primary hover:underline">
              Upload a resume
            </Link>{' '}
            first.
          </p>
        )}
        {!canGenerate && (
          <p className="text-sm text-muted-foreground">Paste the job description first.</p>
        )}

        <section className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <FileText className="size-4 text-primary" aria-hidden="true" />
              Tailored resume
            </h3>
            {data?.tailored && (
              <span className="text-xs text-muted-foreground">
                Version {data.tailored.version_no} · {formatDateTime(data.tailored.updated_at)}
              </span>
            )}
          </div>
          {data?.tailored?.warnings.length > 0 && (
            <Badge variant="warning">{data.tailored.warnings.length} check warnings</Badge>
          )}
          <div className="flex flex-wrap gap-2">
            {data?.tailored && (
              <>
                <Link to={`/jobs/${jobId}/tailored`} className={linkClass}>
                  <PenLine aria-hidden="true" />
                  Review & edit
                </Link>
                <a
                  href={data.tailored.download_url}
                  target="_blank"
                  rel="noreferrer"
                  className={linkClass}
                >
                  PDF
                </a>
              </>
            )}
            <Button
              size="sm"
              variant={data?.tailored ? 'outline' : 'default'}
              onClick={() => tailor.start()}
              disabled={tailor.running || noResume || !canGenerate}
            >
              {tailor.running && <LoaderCircle className="animate-spin" />}
              {data?.tailored ? 'Generate again' : 'Generate tailored resume'}
            </Button>
          </div>
          <TaskLine action={tailor} />
        </section>

        <section className="space-y-2 border-t pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <Mail className="size-4 text-primary" aria-hidden="true" />
              Cover letter
            </h3>
            {data?.cover_letter && (
              <Badge variant={data.cover_letter.status === 'final' ? 'success' : 'outline'}>
                {data.cover_letter.status === 'final' ? 'Final' : 'Draft'}
              </Badge>
            )}
          </div>
          <Input
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder="Recipient name (optional — else “Hiring Team”)"
            aria-label="Recipient name"
          />
          <div className="flex flex-wrap gap-2">
            {data?.cover_letter && (
              <>
                <Link to={`/jobs/${jobId}/cover-letter`} className={linkClass}>
                  <PenLine aria-hidden="true" />
                  Review & edit
                </Link>
                {data.cover_letter.download_url && (
                  <a
                    href={data.cover_letter.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className={linkClass}
                  >
                    PDF
                  </a>
                )}
              </>
            )}
            <Button
              size="sm"
              variant={data?.cover_letter ? 'outline' : 'default'}
              onClick={() => letter.start()}
              disabled={letter.running || noResume || !canGenerate}
            >
              {letter.running && <LoaderCircle className="animate-spin" />}
              {data?.cover_letter ? 'Write a new one' : 'Generate cover letter'}
            </Button>
          </div>
          {data?.tailored && !data?.cover_letter && (
            <p className="text-xs text-muted-foreground">Uses your tailored resume for this job.</p>
          )}
          <TaskLine action={letter} />
        </section>
      </CardContent>
    </Card>
  )
}
