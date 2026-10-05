import { Mic } from 'lucide-react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatRelative } from '@/lib/format'

import { STATUS_LABELS, VERDICT } from '../api'
import { useInterviews } from '../hooks'
import { MockInterviewButton } from './MockInterviewButton'

/** Job page: practise a voice screen for this job; earlier attempts with their scores. */
export function MockInterviewCard({ job }) {
  const interviews = useInterviews(job.id)
  const items = (interviews.data ?? []).slice(0, 4)
  const usable = job.description_quality !== 'missing'
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-4 text-primary" aria-hidden="true" />
          Mock interview
        </CardTitle>
        <CardDescription>
          A short voice screen with an AI interviewer, based on this job and your resume, with a
          scored report.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {usable ? (
          <MockInterviewButton job={job} variant="default" />
        ) : (
          <p className="text-sm text-muted-foreground">Paste the job description first.</p>
        )}
        {items.length > 0 && (
          <ul className="space-y-1 text-sm">
            {items.map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-2">
                <Link to={`/interviews/${i.id}`} className="hover:underline">
                  {formatRelative(i.started_at ?? i.created_at)}
                </Link>
                {i.verdict ? (
                  <Badge variant={VERDICT[i.verdict].variant}>
                    {i.overall_score} · {VERDICT[i.verdict].label}
                  </Badge>
                ) : (
                  <span className="text-xs text-muted-foreground">{STATUS_LABELS[i.status]}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
