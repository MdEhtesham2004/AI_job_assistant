import { Gauge, LoaderCircle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { scoreTone } from '@/features/resumes/score'
import { cn } from '@/lib/utils'

import { DECISION_LABELS } from '../api'
import { useAnalyzeJob } from '../hooks'

const TONE = {
  success: 'border-success/40 bg-success/10 text-success',
  warning: 'border-warning/40 bg-warning/10 text-warning',
  destructive: 'border-destructive/40 bg-destructive/10 text-destructive',
}

export function MatchScoreBadge({ score, decision, stale }) {
  if (score === null || score === undefined) return null
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold',
        stale ? 'border-dashed text-muted-foreground' : TONE[scoreTone(score)],
      )}
      title={stale ? 'Scored with an older resume version' : DECISION_LABELS[decision]}
    >
      {score}% match
      {stale ? ' · older resume' : decision ? ` · ${DECISION_LABELS[decision]}` : ''}
    </span>
  )
}

/** Score badge, or a small "Get match score" button when the job has none (on demand). */
export function MatchScoreAction({ job }) {
  const analyze = useAnalyzeJob(job.id)
  const scored = job.match_score !== null && job.match_score !== undefined

  if (analyze.running) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
        <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
        Scoring…
      </span>
    )
  }
  if (scored && !job.score_stale) {
    return <MatchScoreBadge score={job.match_score} decision={job.decision} />
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      {scored && <MatchScoreBadge score={job.match_score} decision={job.decision} stale />}
      <Button
        variant="outline"
        size="sm"
        className="h-6 px-2 text-xs"
        disabled={job.description_quality === 'missing'}
        title={
          job.description_quality === 'missing'
            ? 'Paste the job description first'
            : 'Compare this job with your active resume'
        }
        onClick={() => analyze.start(Boolean(scored))}
        aria-label={`${scored ? 'Rescore' : 'Get match score for'} ${job.title}`}
      >
        {scored ? <RefreshCw /> : <Gauge />}
        {scored ? 'Rescore' : 'Get match score'}
      </Button>
      {analyze.task?.status === 'failed' && (
        <span role="alert" className="text-xs text-destructive">
          {analyze.task.error}
        </span>
      )}
    </span>
  )
}
