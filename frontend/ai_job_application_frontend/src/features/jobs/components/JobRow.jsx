import { Bookmark, BookmarkCheck, ExternalLink, EyeOff, RotateCcw } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { formatRelative } from '@/lib/format'

import { useSetJobState } from '../hooks'
import { JobStateBadge, QualityBadge } from './JobBadges'

/** One job in a list: title, company, place, freshness, state and quick actions. */
export function JobRow({ job, label }) {
  const setState = useSetJobState()
  const change = (state) => setState.mutate({ id: job.id, state })
  const hidden = job.state === 'skipped' || job.state === 'archived'

  return (
    <li className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <Link to={`/jobs/${job.id}`} className="font-medium hover:text-primary hover:underline">
          {job.title}
        </Link>
        <p className="truncate text-sm text-muted-foreground">
          {job.company}
          {job.location ? ` · ${job.location}` : ''}
          {job.is_remote ? ' · Remote' : ''}
          {job.posted_at ? ` · posted ${formatRelative(job.posted_at)}` : ''}
        </p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {label}
          <JobStateBadge state={job.state} />
          <QualityBadge quality={job.description_quality} />
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {job.apply_url && (
          <a
            href={job.apply_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-sm hover:bg-accent [&_svg]:size-4"
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
