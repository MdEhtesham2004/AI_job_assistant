import {
  ArrowLeft,
  Download,
  ExternalLink,
  FileCheck,
  Gauge,
  IdCard,
  LoaderCircle,
  RefreshCw,
  Sparkles,
} from 'lucide-react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { KIND_LABELS, PDF_MIME, resumesApi } from '@/features/resumes/api'
import { AtsReport } from '@/features/resumes/components/AtsReport'
import { CopyButton } from '@/features/resumes/components/CopyButton'
import { ParsedResumeView } from '@/features/resumes/components/ParsedResumeView'
import { ParseStatusBadge } from '@/features/resumes/components/ParseStatusBadge'
import { ResumeActionButton } from '@/features/resumes/components/ResumeActionButton'
import { useActivateVersion, useResumeAction, useResumeVersion } from '@/features/resumes/hooks'
import { formatBytes, formatDateTime } from '@/lib/format'

const linkClass =
  'inline-flex h-9 items-center gap-2 rounded-md border bg-card px-4 text-sm font-medium hover:bg-accent [&_svg]:size-4'

export default function ResumeVersionPage() {
  const { versionId } = useParams()
  const query = useResumeVersion(versionId)
  const version = query.data

  return (
    <>
      <Link
        to="/resumes"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All versions
      </Link>
      {query.isPending && <p className="text-muted-foreground">Loading…</p>}
      {query.isError && <p className="text-destructive">{query.error.message}</p>}
      {version && <VersionDetail version={version} />}
    </>
  )
}

function VersionDetail({ version }) {
  const activate = useActivateVersion()
  const runningId = (type) => version.active_tasks.find((t) => t.type === type)?.id
  const parsed = version.parse_status === 'parsed'

  return (
    <>
      <PageHeader
        title={`Version ${version.version_no}`}
        description={`${version.file_name} · ${formatBytes(version.file_size)} · ${formatDateTime(version.created_at)}`}
        actions={
          <>
            {version.mime_type === PDF_MIME && (
              <a href={version.download_url} target="_blank" rel="noreferrer" className={linkClass}>
                <ExternalLink aria-hidden="true" />
                Preview
              </a>
            )}
            <a href={version.download_url} download={version.file_name} className={linkClass}>
              <Download aria-hidden="true" />
              Download
            </a>
            {!version.is_active && (
              <Button onClick={() => activate.mutate(version.id)} disabled={activate.isPending}>
                <FileCheck />
                Set active
              </Button>
            )}
          </>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{KIND_LABELS[version.kind] ?? version.kind}</Badge>
        {version.is_active && <Badge variant="success">Active</Badge>}
        <ParseStatusBadge status={version.parse_status} />
        {version.derived_from_id && (
          <Link
            to={`/resumes/${version.derived_from_id}`}
            className="text-sm text-primary hover:underline"
          >
            Improved from an earlier version
          </Link>
        )}
      </div>

      {version.parse_status === 'pending' && (
        <Card className="mb-6">
          <CardContent className="flex items-center gap-3 p-5 text-sm">
            <LoaderCircle className="size-5 animate-spin text-primary" aria-hidden="true" />
            Reading your resume with AI — this usually takes 10–30 seconds.
          </CardContent>
        </Card>
      )}
      {version.parse_status === 'failed' && (
        <ParseFailed version={version} runningTaskId={runningId('resume_parse')} />
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          <AtsCard version={version} runningId={runningId} parsed={parsed} />
          {version.ats_report?.linkedin_summary && (
            <LinkedInCard summary={version.ats_report.linkedin_summary} />
          )}
        </div>
        {parsed && version.parsed && (
          <Card>
            <CardHeader>
              <CardTitle>Parsed resume</CardTitle>
              <CardDescription>What the AI read from your file.</CardDescription>
            </CardHeader>
            <CardContent>
              <ParsedResumeView parsed={version.parsed} />
            </CardContent>
          </Card>
        )}
      </div>
    </>
  )
}

function ParseFailed({ version, runningTaskId }) {
  const retry = useResumeAction(resumesApi.parse, {
    versionId: version.id,
    runningTaskId,
    label: 'Resume parsing',
  })
  return (
    <Card className="mb-6 border-destructive/40">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
        <p className="text-sm text-destructive">
          We could not read this resume: {version.parse_error ?? 'unknown error'}
        </p>
        <ResumeActionButton action={retry} icon={RefreshCw}>
          Try again
        </ResumeActionButton>
      </CardContent>
    </Card>
  )
}

function AtsCard({ version, runningId, parsed }) {
  const report = version.ats_report
  const ats = useResumeAction(resumesApi.ats, {
    versionId: version.id,
    runningTaskId: runningId('resume_ats'),
    label: 'ATS analysis',
  })
  const improve = useResumeAction(resumesApi.improve, {
    versionId: version.id,
    runningTaskId: runningId('resume_improve'),
    label: 'Improved resume',
  })
  const linkedin = useResumeAction(resumesApi.linkedin, {
    versionId: version.id,
    runningTaskId: runningId('resume_linkedin'),
    label: 'LinkedIn summary',
  })
  const improvedId = improve.task?.status === 'succeeded' ? improve.task.result?.version_id : null

  return (
    <Card>
      <CardHeader>
        <CardTitle>ATS report</CardTitle>
        <CardDescription>
          {report
            ? `General ATS quality · analysed ${formatDateTime(report.created_at)}`
            : 'How well applicant-tracking software can read and rank this resume.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {report ? (
          <AtsReport report={report} />
        ) : (
          <p className="text-sm text-muted-foreground">No analysis yet.</p>
        )}
        <div className="flex flex-wrap items-start gap-3 border-t pt-4">
          <ResumeActionButton action={ats} icon={Gauge} variant={report ? 'outline' : 'default'}>
            {report ? 'Analyse again' : 'Run ATS analysis'}
          </ResumeActionButton>
          {report && parsed && (
            <>
              <ResumeActionButton action={improve} icon={Sparkles} variant="default">
                Generate improved resume
              </ResumeActionButton>
              <ResumeActionButton action={linkedin} icon={IdCard}>
                {report.linkedin_summary ? 'New LinkedIn summary' : 'Generate LinkedIn summary'}
              </ResumeActionButton>
            </>
          )}
        </div>
        {improvedId && (
          <p className="text-sm">
            Your improved resume is saved as a new version.{' '}
            <Link
              to={`/resumes/${improvedId}`}
              className="font-medium text-primary hover:underline"
            >
              Open it
            </Link>
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function LinkedInCard({ summary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>LinkedIn summary</CardTitle>
        <CardDescription>Paste these into your LinkedIn profile.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-1 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Headline</h3>
            <CopyButton text={summary.headline} label="Copy headline" />
          </div>
          <p className="rounded-md bg-muted/50 p-3 text-sm">{summary.headline}</p>
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">About</h3>
            <CopyButton text={summary.about} label="Copy about" />
          </div>
          <p className="whitespace-pre-line rounded-md bg-muted/50 p-3 text-sm">{summary.about}</p>
        </div>
      </CardContent>
    </Card>
  )
}
