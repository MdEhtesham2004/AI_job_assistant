import { ClipboardPaste, LoaderCircle, Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { FormError } from '@/components/common/FormError'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { AnalysisPanel } from '@/features/jobs/components/AnalysisPanel'
import { JobRow } from '@/features/jobs/components/JobRow'
import { ScoringBar } from '@/features/jobs/components/ScoringBar'
import {
  useAnalysisSummary,
  useAnalyzeBatch,
  useJob,
  useJobs,
  useScanText,
} from '@/features/jobs/hooks'
import { isActive } from '@/features/tasks/api'
import { useTaskPolling } from '@/features/tasks/hooks'

const MIN_DESCRIPTION = 200

export default function ScanPage() {
  return (
    <>
      <PageHeader
        title="Scan"
        description="Find your best-matching stored jobs, or check how well any job description fits your resume."
      />
      <div className="grid gap-6 xl:grid-cols-2">
        <KeywordScan />
        <PasteScan />
      </div>
    </>
  )
}

/** Keyword + minimum score over the jobs you already have (scores only on click). */
function KeywordScan() {
  const [query, setQuery] = useState(null) // { q, min_score } once submitted
  const view = query ? { q: query.q, min_score: '', sort: 'score' } : null
  const matches = useJobs(
    {
      ...view,
      min_score: query?.min_score === '0' ? '' : query?.min_score,
      page: 1,
      page_size: 50,
    },
    { enabled: Boolean(query) },
  )
  const summary = useAnalysisSummary(view ?? {}, { enabled: Boolean(query) })
  const batch = useAnalyzeBatch()

  const onSubmit = (event) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setQuery({ q: form.get('q').trim(), min_score: form.get('min') })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Search className="size-4 text-primary" aria-hidden="true" />
          Best matches in your jobs
        </CardTitle>
        <CardDescription>Searches title and company of the jobs in your list.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={onSubmit} className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
          <Input name="q" placeholder="e.g. React Native" aria-label="Keyword" />
          <Select name="min" aria-label="Minimum score" defaultValue="0">
            <option value="0">Any score</option>
            <option value="50">≥ 50</option>
            <option value="65">≥ 65</option>
            <option value="85">≥ 85</option>
          </Select>
          <Button type="submit">Scan</Button>
        </form>
        {query && (
          <>
            <ScoringBar summary={summary} batch={batch} onScore={() => batch.start(view)} />
            {Number(query.min_score) > 0 && (
              <p className="text-xs text-muted-foreground">
                Only scored jobs can pass a minimum score — score the others first.
              </p>
            )}
            <ul className="divide-y rounded-lg border">
              {matches.isPending && <li className="px-5 py-6 text-sm">Loading…</li>}
              {matches.data?.items.length === 0 && (
                <li className="px-5 py-6 text-sm text-muted-foreground">No matching jobs.</li>
              )}
              {matches.data?.items.map((job) => (
                <JobRow key={job.id} job={job} />
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  )
}

/** Paste any job description and score it (saved privately as "Added by me"). */
function PasteScan() {
  const scan = useScanText()
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [description, setDescription] = useState('')
  const started = scan.data
  const task = useTaskPolling(started?.task_id ?? null).data
  const done = task && !isActive(task)

  const onSubmit = (event) => {
    event.preventDefault()
    scan.mutate({
      title: title.trim() || 'Pasted job',
      company: company.trim() || 'Unknown company',
      description: description.trim(),
    })
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ClipboardPaste className="size-4 text-primary" aria-hidden="true" />
            Paste a job description
          </CardTitle>
          <CardDescription>
            It is saved as a private job (only you see it), so you can apply to it later.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-3">
            <FormError message={scan.error?.message} />
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="scan-title">Job title</Label>
                <Input id="scan-title" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="scan-company">Company</Label>
                <Input
                  id="scan-company"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="scan-description">Job description</Label>
              <Textarea
                id="scan-description"
                rows={10}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {description.trim().length < MIN_DESCRIPTION
                  ? `At least ${MIN_DESCRIPTION} characters (${description.trim().length} so far).`
                  : 'Ready — scoring uses about $0.001 of AI.'}
              </p>
            </div>
            <Button
              type="submit"
              disabled={scan.isPending || description.trim().length < MIN_DESCRIPTION}
            >
              {scan.isPending || (task && isActive(task)) ? (
                <LoaderCircle className="animate-spin" />
              ) : null}
              Score this job
            </Button>
          </form>
        </CardContent>
      </Card>

      {started && task?.status === 'failed' && (
        <p role="alert" className="text-sm text-destructive">
          {task.error}
        </p>
      )}
      {done && task.status === 'succeeded' && <ScanResult jobId={started.job_id} />}
    </div>
  )
}

/** Mounted only after scoring finished, so the job is fetched with its new score. */
function ScanResult({ jobId }) {
  const job = useJob(jobId)
  if (!job.data) return null
  return (
    <>
      <AnalysisPanel job={job.data} />
      <Link to={`/jobs/${jobId}`} className="text-sm text-primary hover:underline">
        Open the saved job
      </Link>
    </>
  )
}
