import { ArrowLeft, ExternalLink, PenLine, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DiffText } from '@/features/jobs/components/DiffText'
import { useEditTailored, useJobDocuments } from '@/features/jobs/hooks'
import { closestBullet, fromEditForm, matchingJob, toEditForm } from '@/features/jobs/resumeCompare'
import { cn } from '@/lib/utils'

const linkClass =
  'inline-flex h-9 items-center gap-2 rounded-md border bg-card px-4 text-sm font-medium hover:bg-accent [&_svg]:size-4'

export default function TailoredResumePage() {
  const { jobId } = useParams()
  const docs = useJobDocuments(jobId)
  const [editing, setEditing] = useState(false)
  const data = docs.data

  return (
    <>
      <Link
        to={`/jobs/${jobId}`}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to the job
      </Link>
      {docs.isPending && <p className="text-muted-foreground">Loading…</p>}
      {docs.isError && <p className="text-destructive">{docs.error.message}</p>}
      {data && !data.tailored && (
        <p className="text-muted-foreground">
          No tailored resume yet — generate one on the job page.
        </p>
      )}
      {data?.tailored && (
        <>
          <PageHeader
            title="Tailored resume"
            description={`${data.job_title} · ${data.company} · version ${data.tailored.version_no}`}
            actions={
              <>
                <a
                  href={data.tailored.download_url}
                  target="_blank"
                  rel="noreferrer"
                  className={linkClass}
                >
                  <ExternalLink aria-hidden="true" />
                  Open PDF
                </a>
                <Button
                  variant={editing ? 'outline' : 'default'}
                  onClick={() => setEditing(!editing)}
                >
                  <PenLine />
                  {editing ? 'Back to comparison' : 'Edit'}
                </Button>
              </>
            }
          />
          <Warnings warnings={data.tailored.warnings} />
          {editing ? (
            <Editor
              key={data.tailored.updated_at}
              tailored={data.tailored}
              onSaved={() => setEditing(false)}
            />
          ) : (
            <Comparison data={data} />
          )}
        </>
      )}
    </>
  )
}

function Warnings({ warnings }) {
  if (!warnings.length) return null
  return (
    <div
      role="alert"
      className="mb-6 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm"
    >
      <p className="mb-1 flex items-center gap-2 font-semibold">
        <TriangleAlert className="size-4 text-warning" aria-hidden="true" />
        Not found in your original resume
      </p>
      <p className="mb-2 text-muted-foreground">
        Only send this if every item below is really true for you.
      </p>
      <ul className="list-disc pl-5">
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  )
}

function Column({ title, children }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 text-sm">{children}</CardContent>
    </Card>
  )
}

function Section({ title, children }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  )
}

function Comparison({ data }) {
  const tailored = data.tailored.parsed
  const master = data.tailored_from?.parsed
  const emphasized = new Set(data.tailored.emphasized_skills.map((s) => s.toLowerCase()))

  return (
    <>
      <p className="mb-4 text-sm text-muted-foreground">
        <mark className="rounded bg-success/20 px-1 text-foreground">Highlighted</mark> = new
        wording · <span className="font-semibold text-primary">Blue skills</span> = mentioned in the
        job.
      </p>
      <div className="grid gap-6 lg:grid-cols-2">
        <Column
          title={`Your resume${data.tailored_from ? ` (version ${data.tailored_from.version_no})` : ''}`}
        >
          {master ? (
            <>
              <Section title="Summary">
                <p>{master.summary ?? '—'}</p>
              </Section>
              <Section title="Skills">
                <p>{master.skills.join(', ')}</p>
              </Section>
              <Section title="Experience">
                {master.experience.map((job, index) => (
                  <div key={index} className="mb-3">
                    <p className="font-medium">
                      {job.title} · {job.company}
                    </p>
                    <ul className="list-disc pl-5">
                      {job.highlights.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </Section>
            </>
          ) : (
            <p className="text-muted-foreground">The original version is not available.</p>
          )}
        </Column>
        <Column title="Tailored for this job">
          <Section title="Summary">
            <p>
              <DiffText before={master?.summary} after={tailored.summary} />
            </p>
          </Section>
          <Section title="Skills">
            <p>
              {tailored.skills.map((skill, index) => (
                <span key={skill}>
                  <span
                    className={cn(
                      emphasized.has(skill.toLowerCase()) && 'font-semibold text-primary',
                    )}
                  >
                    {skill}
                  </span>
                  {index < tailored.skills.length - 1 ? ', ' : ''}
                </span>
              ))}
            </p>
          </Section>
          <Section title="Experience">
            {tailored.experience.map((job, index) => {
              const original = master ? matchingJob(job, master.experience) : null
              return (
                <div key={index} className="mb-3">
                  <p className="font-medium">
                    {job.title} · {job.company}
                  </p>
                  <ul className="list-disc pl-5">
                    {job.highlights.map((item) => (
                      <li key={item}>
                        <DiffText
                          before={original ? closestBullet(item, original.highlights) : ''}
                          after={item}
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </Section>
        </Column>
      </div>
    </>
  )
}

function Editor({ tailored, onSaved }) {
  const save = useEditTailored()
  const [form, setForm] = useState(() => toEditForm(tailored.parsed))
  const set = (changes) => setForm((current) => ({ ...current, ...changes }))

  return (
    <Card>
      <CardContent className="space-y-5 pt-5">
        <p className="text-sm text-muted-foreground">
          Saving re-creates the PDF. Name and contact details always come from your original resume.
        </p>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tailored-summary">Summary</Label>
          <Textarea
            id="tailored-summary"
            rows={4}
            value={form.summary}
            onChange={(e) => set({ summary: e.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tailored-skills">Skills (comma separated, most relevant first)</Label>
          <Textarea
            id="tailored-skills"
            rows={2}
            value={form.skills}
            onChange={(e) => set({ skills: e.target.value })}
          />
        </div>
        {tailored.parsed.experience.map((job, index) => (
          <div key={index} className="flex flex-col gap-1.5">
            <Label htmlFor={`tailored-job-${index}`}>
              {job.title} · {job.company} — one bullet per line
            </Label>
            <Textarea
              id={`tailored-job-${index}`}
              rows={4}
              value={form.highlights[index]}
              onChange={(e) =>
                set({
                  highlights: form.highlights.map((value, i) =>
                    i === index ? e.target.value : value,
                  ),
                })
              }
            />
          </div>
        ))}
        <Button
          disabled={save.isPending}
          onClick={() =>
            save.mutate(
              { versionId: tailored.id, parsed: fromEditForm(tailored.parsed, form) },
              { onSuccess: onSaved },
            )
          }
        >
          {save.isPending ? 'Saving…' : 'Save and update PDF'}
        </Button>
      </CardContent>
    </Card>
  )
}
