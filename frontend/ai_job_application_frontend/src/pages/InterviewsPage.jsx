import { Mic } from 'lucide-react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { useUsage } from '@/features/dashboard/api'
import { ROUND_LABELS, STATUS_LABELS, VERDICT } from '@/features/interviews/api'
import { useInterviews } from '@/features/interviews/hooks'
import { formatRelative } from '@/lib/format'

export default function InterviewsPage() {
  const interviews = useInterviews()
  const quota = useUsage().data?.interviews_month
  const items = interviews.data ?? []

  return (
    <>
      <PageHeader
        title="Mock interviews"
        description={
          'Practise a short voice screen for any job: open a job and click "Mock interview".' +
          (quota?.limit ? ` ${quota.left} of ${quota.limit} left this month.` : '')
        }
      />
      {interviews.isPending && <p className="text-muted-foreground">Loading…</p>}
      {!interviews.isPending && items.length === 0 && (
        <Card>
          <CardContent className="flex items-center gap-3 py-6 text-sm text-muted-foreground">
            <Mic className="size-5" aria-hidden="true" />
            No interviews yet. Open a job from{' '}
            <Link to="/jobs" className="font-medium text-primary hover:underline">
              Jobs
            </Link>{' '}
            and start one.
          </CardContent>
        </Card>
      )}
      {items.length > 0 && (
        <Card>
          <CardContent className="overflow-x-auto pt-4">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 font-medium">Job</th>
                  <th className="py-1 font-medium">Round</th>
                  <th className="py-1 font-medium">Result</th>
                  <th className="py-1 text-right font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.id} className="border-t">
                    <td className="py-2">
                      <Link to={`/interviews/${i.id}`} className="font-medium hover:underline">
                        {i.job.title}
                      </Link>
                      <div className="text-xs text-muted-foreground">{i.job.company}</div>
                    </td>
                    <td className="py-2">{ROUND_LABELS[i.round] ?? i.round}</td>
                    <td className="py-2">
                      {i.verdict ? (
                        <span className="flex items-center gap-2">
                          <span className="tabular-nums font-semibold">{i.overall_score}</span>
                          <Badge variant={VERDICT[i.verdict].variant}>
                            {VERDICT[i.verdict].label}
                          </Badge>
                        </span>
                      ) : (
                        <span className="text-muted-foreground">{STATUS_LABELS[i.status]}</span>
                      )}
                    </td>
                    <td className="py-2 text-right text-xs text-muted-foreground">
                      {formatRelative(i.started_at ?? i.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </>
  )
}
