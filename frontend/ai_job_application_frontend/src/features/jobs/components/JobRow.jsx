import { Bookmark, BookmarkCheck, ExternalLink, EyeOff, RotateCcw } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { scoreTone } from '@/features/resumes/score'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

import { DECISION_LABELS } from '../api'
import { useSetJobState } from '../hooks'
import { JobStateBadge, QualityBadge } from './JobBadges'
import { MatchScoreAction } from './MatchScore'

const TONE_TEXT = {
  success: 'text-success',
  warning: 'text-warning',
  destructive: 'text-destructive',
}

/** Phase 21: the score is the first thing you read in a row — a big numeral in its own column. */
function ScoreCell({ job }) {
  const scored = job.match_score !== null && job.match_score !== undefined
  const fresh = scored && !job.score_stale
  return (
    <div className="pt-0.5 text-left" aria-hidden={!scored}>
      <span
        className={cn(
          'tabular block text-[1.875rem] font-bold leading-none tracking-tight',
          fresh ? TONE_TEXT[scoreTone(job.match_score)] : 'text-muted-foreground/45',
        )}
      >
        {scored ? job.match_score : '–'}
      </span>
      <span className="mt-1 block text-[0.7rem] text-muted-foreground">
        {fresh ? 'match' : scored ? 'older resume' : 'no score'}
      </span>
    </div>
  )
}

/** One job in a list: score, title, company, place, freshness, state and quick actions. */
export function JobRow({ job, label }) {
  const setState = useSetJobState()
  const change = (state) => setState.mutate({ id: job.id, state })
  const hidden = job.state === 'skipped' || job.state === 'archived'
  const fresh = job.match_score !== null && job.match_score !== undefined && !job.score_stale

  return (
    <li className="grid grid-cols-[3.75rem_minmax(0,1fr)] gap-x-4 gap-y-2 px-5 py-4 sm:grid-cols-[3.75rem_minmax(0,1fr)_auto] sm:items-center">
      <ScoreCell job={job} />
      <div className="min-w-0">
        <Link
          to={`/jobs/${job.id}`}
          className="text-[1rem] font-semibold leading-snug hover:text-primary hover:underline"
        >
          {job.title}
        </Link>
        <p className="truncate text-sm text-muted-foreground">
          {job.company}
          {job.location ? ` · ${job.location}` : ''}
          {job.is_remote ? ' · Remote' : ''}
          {job.posted_at ? ` · posted ${formatRelative(job.posted_at)}` : ''}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {fresh && job.decision && (
            <span className={cn('text-xs font-semibold', TONE_TEXT[scoreTone(job.match_score)])}>
              {DECISION_LABELS[job.decision]}
            </span>
          )}
          {label}
          {/* Only what's worth noticing: "Analyzed" is shown by the score, a full description is normal. */}
          {job.state !== 'analyzed' && <JobStateBadge state={job.state} />}
          {job.description_quality !== 'complete' && (
            <QualityBadge quality={job.description_quality} />
          )}
          {!fresh && <MatchScoreAction job={job} hideBadge />}
        </div>
      </div>
      <div className="col-start-2 flex shrink-0 items-center gap-1 sm:col-start-auto">
        {job.apply_url && (
          <a
            href={job.apply_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-sm font-medium hover:bg-accent [&_svg]:size-4"
            aria-label={`Apply for ${job.title} (opens a new tab)`}
          >
            <ExternalLink aria-hidden="true" />
            Apply
          </a>
        )}
        {hidden ? (
          <Button variant="ghost" size="sm" onClick={() => change('new')} aria-label="Restore">
            <RotateCcw />
            Restore
          </Button>
        ) : (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => change(job.state === 'saved' ? 'new' : 'saved')}
              aria-label={job.state === 'saved' ? `Unsave ${job.title}` : `Save ${job.title}`}
            >
              {job.state === 'saved' ? <BookmarkCheck /> : <Bookmark />}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => change('skipped')}
              aria-label={`Skip ${job.title}`}
            >
              <EyeOff />
            </Button>
          </>
        )}
      </div>
    </li>
  )
}
