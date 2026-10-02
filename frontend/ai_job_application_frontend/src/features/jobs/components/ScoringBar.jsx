import { Gauge, LoaderCircle } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'

import { COST_PER_SCORE_USD } from '../api'

const cost = (n) => `≈ $${Math.max(0.01, n * COST_PER_SCORE_USD).toFixed(2)}`

/** "Score all" for the current view — only on click, never automatic. */
export function ScoringBar({ summary, batch, saved, onScore }) {
  if (summary.isError) {
    if (summary.error.code !== 'RESUME_REQUIRED') return null
    return (
      <p className="mb-4 text-sm text-muted-foreground">
        Match scores need a parsed resume.{' '}
        <Link to="/resumes" className="text-primary hover:underline">
          Upload one
        </Link>
      </p>
    )
  }
  const data = summary.data
  if (!data) return null
  if (batch.running) {
    return (
      <div className="mb-4 flex items-center gap-3 rounded-lg border px-4 py-3 text-sm">
        <LoaderCircle className="size-4 animate-spin text-primary" aria-hidden="true" />
        Scoring jobs…
        <div className="w-48">
          <ProgressBar value={batch.task?.progress ?? 0} status={batch.task?.status ?? 'queued'} />
        </div>
      </div>
    )
  }
  if (data.to_score === 0) return null
  const label = saved
    ? `Score all saved jobs (${data.to_score})`
    : `Score ${data.to_score} job${data.to_score === 1 ? '' : 's'} in this view`
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm">
      <span className="text-muted-foreground">
        {data.to_score} job{data.to_score === 1 ? '' : 's'} here without a match score
        {data.no_description > 0 && ` · ${data.no_description} need a pasted description`}
        {data.over_limit > 0 && ` · ${data.over_limit} more after this batch`}
      </span>
      <Button size="sm" onClick={onScore}>
        <Gauge />
        {label} · {cost(data.to_score)}
      </Button>
    </div>
  )
}
