import { GraduationCap, LoaderCircle } from 'lucide-react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useMakePlan, useSkills } from '@/features/hunt/api'
import { formatRelative } from '@/lib/format'

function Bars({ items, total, label }) {
  const max = Math.max(1, ...items.map((i) => i.jobs))
  return (
    <ul className="space-y-2" aria-label={label}>
      {items.map((item) => (
        <li key={item.skill} className="text-sm">
          <div className="flex justify-between gap-2">
            <span className="font-medium">{item.skill}</span>
            <span className="tabular-nums text-muted-foreground">
              {item.jobs} of {total} jobs
            </span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${(item.jobs / max) * 100}%` }}
            />
          </div>
          {item.examples?.length > 0 && (
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              e.g. {item.examples.join(' · ')}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

export default function SkillsPage() {
  const skills = useSkills()
  const data = skills.data
  const make = useMakePlan(data?.running_task_id)
  const plan = data?.plan

  return (
    <>
      <PageHeader
        title="Skill gaps"
        description="What the jobs you scored ask for that your resume does not show yet — and a plan to close the gap."
      />
      {skills.isPending && <p className="text-muted-foreground">Loading…</p>}
      {data && data.jobs_analyzed === 0 && (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            No scored jobs yet. Score a few jobs in{' '}
            <Link to="/jobs" className="font-medium text-primary hover:underline">
              Jobs
            </Link>{' '}
            and come back.
          </CardContent>
        </Card>
      )}
      {data && data.jobs_analyzed > 0 && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Most requested, not shown yet</CardTitle>
                <CardDescription>Across {data.jobs_analyzed} scored jobs.</CardDescription>
              </CardHeader>
              <CardContent>
                {data.gaps.length ? (
                  <Bars items={data.gaps} total={data.jobs_analyzed} label="Skill gaps" />
                ) : (
                  <p className="text-sm text-muted-foreground">No gaps — nice.</p>
                )}
              </CardContent>
            </Card>
            {data.strengths.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Your strengths</CardTitle>
                </CardHeader>
                <CardContent>
                  <Bars items={data.strengths} total={data.jobs_analyzed} label="Strengths" />
                </CardContent>
              </Card>
            )}
          </div>

          <Card className="h-fit">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <GraduationCap className="size-4 text-primary" aria-hidden="true" />
                2-week learning plan
              </CardTitle>
              <CardDescription>
                {plan
                  ? `Made ${formatRelative(plan.created_at)} for: ${plan.gaps.map((g) => g.skill).join(', ')}.`
                  : 'One focused hour a day for your top gaps, ending with a small project.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              {plan && (
                <>
                  <p>{plan.plan.summary}</p>
                  <ol className="space-y-1.5">
                    {plan.plan.days.map((d) => (
                      <li key={d.day} className="grid grid-cols-[3.5rem_1fr] gap-2">
                        <span className="font-medium tabular-nums">Day {d.day}</span>
                        <span>
                          <span className="font-medium">{d.focus}:</span> {d.task}
                        </span>
                      </li>
                    ))}
                  </ol>
                  <p>
                    <span className="font-medium">Mini project:</span> {plan.plan.mini_project}
                  </p>
                  {plan.plan.resources?.length > 0 && (
                    <div>
                      <p className="font-medium">Resources</p>
                      <ul className="list-disc pl-5">
                        {plan.plan.resources.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="text-muted-foreground">
                    <span className="font-medium text-foreground">In interviews:</span>{' '}
                    {plan.plan.interview_tip}
                  </p>
                </>
              )}
              <Button
                onClick={() => make.start()}
                disabled={make.running || data.gaps.length === 0}
              >
                {make.running && <LoaderCircle className="animate-spin" />}
                {make.running ? 'Writing your plan…' : plan ? 'Make a new plan' : 'Make my plan'}
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </>
  )
}
