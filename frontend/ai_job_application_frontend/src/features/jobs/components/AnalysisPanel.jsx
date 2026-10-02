import { CircleCheck, Gauge, Lightbulb, LoaderCircle, RefreshCw, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScoreGauge } from '@/features/resumes/components/AtsReport'
import { scoreTone, TONE_BG } from '@/features/resumes/score'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

import { DECISION_LABELS } from '../api'
import { useAnalyzeJob } from '../hooks'

const COMPONENTS = [
  ['skills', 'Skills'],
  ['experience', 'Experience'],
  ['technology', 'Technology'],
  ['education', 'Education'],
  ['location', 'Location'],
]

const SENIORITY = {
  below: 'Below the level asked',
  good: 'Right level',
  above: 'Above the level asked',
}

function List({ title, icon: Icon, tone, items, empty }) {
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Icon className={cn('size-4', tone)} aria-hidden="true" />
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="text-muted-foreground">•</span>
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Match analysis on the job page: score, components, skills, tips — or "Get match score". */
export function AnalysisPanel({ job }) {
  const running = job.active_tasks.find((t) => t.type === 'job_analyze')
  const analyze = useAnalyzeJob(job.id, running?.id)
  const analysis = job.analysis
  const canScore = job.description_quality !== 'missing'

  return (
    <Card>
      <CardHeader>
        <CardTitle>Match with your resume</CardTitle>
        <CardDescription>
          {analysis
            ? `Scored ${formatDateTime(analysis.updated_at)} · an internal signal, not a hiring prediction`
            : 'Compares this job with your active resume. Runs only when you ask (≈ $0.001).'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {job.score_stale && (
          <p className="rounded-md border border-warning/40 bg-warning/10 p-2 text-sm">
            This score was made with an older resume version.
          </p>
        )}
        {analysis && (
          <>
            <div className="flex flex-col items-center gap-5 sm:flex-row">
              <ScoreGauge score={analysis.match_score} size={112} />
              <div className="w-full flex-1 space-y-2">
                <p className="text-sm font-semibold">
                  {DECISION_LABELS[analysis.decision]}
                  {analysis.seniority_fit && (
                    <span className="font-normal text-muted-foreground">
                      {' '}
                      · {SENIORITY[analysis.seniority_fit] ?? analysis.seniority_fit}
                    </span>
                  )}
                </p>
                {COMPONENTS.map(([key, label]) => {
                  const value = analysis.component_scores[key] ?? 0
                  return (
                    <div key={key}>
                      <div className="flex justify-between text-xs">
                        <span>
                          {label}{' '}
                          <span className="text-muted-foreground">
                            ({analysis.weights_used[key] ?? 0}%)
                          </span>
                        </span>
                        <span className="font-medium">{value}</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className={cn('h-full rounded-full', TONE_BG[scoreTone(value)])}
                          style={{ width: `${value}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <List
                title="Matching skills"
                icon={CircleCheck}
                tone="text-success"
                items={analysis.matched_skills}
                empty="None found."
              />
              <List
                title="Missing skills"
                icon={TriangleAlert}
                tone="text-warning"
                items={analysis.missing_skills}
                empty="No obvious gaps."
              />
            </div>
            <List
              title="Recommendations"
              icon={Lightbulb}
              tone="text-primary"
              items={analysis.recommendations}
              empty="No recommendations."
            />
            {analysis.red_flags.length > 0 && (
              <List
                title="Red flags"
                icon={TriangleAlert}
                tone="text-destructive"
                items={analysis.red_flags}
                empty=""
              />
            )}
          </>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t pt-4">
          <Button
            variant={analysis && !job.score_stale ? 'outline' : 'default'}
            onClick={() => analyze.start(Boolean(analysis))}
            disabled={analyze.running || !canScore}
          >
            {analyze.running ? (
              <LoaderCircle className="animate-spin" />
            ) : analysis ? (
              <RefreshCw />
            ) : (
              <Gauge />
            )}
            {analysis ? 'Score again' : 'Get match score'}
          </Button>
          {!canScore && (
            <span className="text-sm text-muted-foreground">Paste the job description first.</span>
          )}
          {analyze.running && analyze.task && (
            <div className="w-40">
              <ProgressBar value={analyze.task.progress} status={analyze.task.status} />
            </div>
          )}
        </div>
        {analyze.task?.status === 'failed' && (
          <p role="alert" className="text-sm text-destructive">
            {analyze.task.error}{' '}
            {/resume/i.test(analyze.task.error ?? '') && (
              <Link to="/resumes" className="text-primary hover:underline">
                Go to Resumes
              </Link>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
