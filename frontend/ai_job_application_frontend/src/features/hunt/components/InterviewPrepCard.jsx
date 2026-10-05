import { BookOpenCheck, LoaderCircle, RefreshCw } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { MockInterviewButton } from '@/features/interviews/components/MockInterviewButton'
import { formatRelative } from '@/lib/format'

import { useMakePrep, usePrep } from '../api'

/** Job / application page: the interview prep pack — open it, practise it, refresh it. */
export function InterviewPrepCard({ job, highlight = false }) {
  const prep = usePrep(job.id)
  const data = prep.data
  const make = useMakePrep(job.id, data?.running_task_id)
  const pack = data?.pack
  const usable = job.description_quality !== 'missing'

  return (
    <Card className={highlight ? 'border-primary' : undefined}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpenCheck className="size-4 text-primary" aria-hidden="true" />
          Interview prep
        </CardTitle>
        <CardDescription>
          {pack
            ? `Ready ${formatRelative(data.updated_at)}: ${pack.likely_questions.length} likely questions, ${pack.star_stories.length} STAR stories and questions to ask.`
            : 'Likely questions, your STAR stories from your resume, honest answers to gaps and questions to ask — made automatically when an application reaches Interview.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {pack && (
          <>
            <Link
              to={`/jobs/${job.id}/prep`}
              className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Open prep
            </Link>
            <MockInterviewButton job={job} fromPrep />
          </>
        )}
        {usable ? (
          <Button
            variant={pack ? 'ghost' : 'default'}
            onClick={() => make.start()}
            disabled={make.running}
          >
            {make.running ? <LoaderCircle className="animate-spin" /> : pack && <RefreshCw />}
            {make.running ? 'Preparing…' : pack ? 'Refresh' : 'Prepare for interview'}
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">Paste the job description first.</p>
        )}
      </CardContent>
    </Card>
  )
}
