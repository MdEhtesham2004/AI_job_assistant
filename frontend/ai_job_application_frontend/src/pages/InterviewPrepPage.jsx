import { ArrowLeft, Download, LoaderCircle } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useMakePrep, usePrep } from '@/features/hunt/api'
import { MockInterviewButton } from '@/features/interviews/components/MockInterviewButton'
import { useJob } from '@/features/jobs/hooks'

function Section({ title, children }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">{children}</CardContent>
    </Card>
  )
}

function Bullets({ items }) {
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}

export default function InterviewPrepPage() {
  const { jobId } = useParams()
  const job = useJob(jobId).data
  const prep = usePrep(jobId)
  const data = prep.data
  const make = useMakePrep(jobId, data?.running_task_id)
  const pack = data?.pack

  return (
    <>
      <Link
        to={`/jobs/${jobId}`}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to the job
      </Link>
      <PageHeader
        title={`Interview prep${job ? ` — ${job.title}` : ''}`}
        description={job?.company}
        actions={
          pack && (
            <>
              {job && <MockInterviewButton job={job} fromPrep variant="default" />}
              {data.pdf_url && (
                <Button variant="outline" onClick={() => window.open(data.pdf_url, '_blank')}>
                  <Download />
                  PDF
                </Button>
              )}
            </>
          )
        }
      />
      {prep.isPending && <p className="text-muted-foreground">Loading…</p>}
      {data && !pack && (
        <Card className="max-w-2xl">
          <CardContent className="space-y-3 py-6 text-sm">
            {make.running ? (
              <p className="flex items-center gap-2">
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                Preparing your pack — this takes about half a minute…
              </p>
            ) : (
              <>
                <p>No prep pack for this job yet.</p>
                <Button onClick={() => make.start()}>Prepare for interview</Button>
              </>
            )}
          </CardContent>
        </Card>
      )}
      {pack && (
        <div className="flex flex-col gap-4">
          <Section title="The role">
            <p>{pack.role_summary}</p>
            <p className="font-medium">What they value most</p>
            <Bullets items={pack.what_they_value} />
          </Section>

          <Section title="Your fit">
            <table className="w-full">
              <tbody>
                {pack.your_fit.map((f) => (
                  <tr key={f.requirement} className="border-t first:border-t-0">
                    <td className="py-1.5 pr-3 align-top font-medium">{f.requirement}</td>
                    <td
                      className={
                        f.evidence.startsWith('Not shown')
                          ? 'py-1.5 text-warning'
                          : 'py-1.5 text-muted-foreground'
                      }
                    >
                      {f.evidence}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title="Likely questions">
            <ol className="space-y-3">
              {pack.likely_questions.map((q, i) => (
                <li key={q.question}>
                  <p className="font-medium">
                    {i + 1}. {q.question}
                  </p>
                  <p className="text-xs text-muted-foreground">{q.why}</p>
                  <p>{q.how_to_answer}</p>
                </li>
              ))}
            </ol>
          </Section>

          <Section title="Your STAR stories">
            {pack.check?.length > 0 && (
              <p className="text-xs text-warning">
                Check these numbers — they are not in your resume: {pack.check.join(', ')}
              </p>
            )}
            <div className="grid gap-3 lg:grid-cols-3">
              {pack.star_stories.map((s) => (
                <div key={s.title} className="rounded-md border p-3">
                  <p className="font-medium">{s.title}</p>
                  <dl className="mt-1 space-y-1">
                    {[
                      ['Situation', s.situation],
                      ['Task', s.task],
                      ['Action', s.action],
                      ['Result', s.result],
                    ].map(([k, v]) => (
                      <div key={k}>
                        <dt className="inline font-medium">{k}: </dt>
                        <dd className="inline">{v}</dd>
                      </div>
                    ))}
                  </dl>
                  {s.use_for?.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Use for: {s.use_for.join(' · ')}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </Section>

          {pack.gaps.length > 0 && (
            <Section title="Gaps to expect">
              {pack.gaps.map((g) => (
                <p key={g.gap}>
                  <span className="font-medium">{g.gap}:</span> {g.honest_answer}
                </p>
              ))}
            </Section>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Questions to ask them">
              <Bullets items={pack.questions_to_ask} />
            </Section>
            <Section title="The day before">
              <Bullets items={pack.checklist} />
            </Section>
          </div>
        </div>
      )}
    </>
  )
}
