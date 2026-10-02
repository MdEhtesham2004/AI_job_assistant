import { ArrowLeft, CircleCheck, ExternalLink, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { CopyButton } from '@/features/resumes/components/CopyButton'
import { useEditCoverLetter, useJobDocuments } from '@/features/jobs/hooks'

const linkClass =
  'inline-flex h-9 items-center gap-2 rounded-md border bg-card px-4 text-sm font-medium hover:bg-accent [&_svg]:size-4'

const words = (text) => (text.match(/\S+/g) ?? []).length

export default function CoverLetterPage() {
  const { jobId } = useParams()
  const docs = useJobDocuments(jobId)
  const letter = docs.data?.cover_letter

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
      {docs.data && !letter && (
        <p className="text-muted-foreground">No cover letter yet — generate one on the job page.</p>
      )}
      {letter && (
        <Editor
          key={letter.updated_at}
          letter={letter}
          title={docs.data.job_title}
          company={docs.data.company}
        />
      )}
    </>
  )
}

function Editor({ letter, title, company }) {
  const save = useEditCoverLetter()
  const [text, setText] = useState(letter.content_md)
  const dirty = text !== letter.content_md
  const final = letter.status === 'final'

  return (
    <>
      <PageHeader
        title="Cover letter"
        description={`${title} · ${company}`}
        actions={
          <>
            <Badge variant={final ? 'success' : 'outline'}>{final ? 'Final' : 'Draft'}</Badge>
            {letter.download_url && (
              <a href={letter.download_url} target="_blank" rel="noreferrer" className={linkClass}>
                <ExternalLink aria-hidden="true" />
                Open PDF
              </a>
            )}
          </>
        }
      />
      {letter.warnings.length > 0 && (
        <div
          role="alert"
          className="mb-6 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm"
        >
          <p className="mb-1 flex items-center gap-2 font-semibold">
            <TriangleAlert className="size-4 text-warning" aria-hidden="true" />
            Please check before sending
          </p>
          <ul className="list-disc pl-5">
            {letter.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mb-4 text-sm text-muted-foreground">
        Checked automatically for placeholders, invented numbers, skills you lack and naming the
        company and role. Vague claims can still slip through — read it before sending.
      </p>
      <Card>
        <CardContent className="space-y-3 pt-5">
          <Textarea
            aria-label="Cover letter text"
            rows={20}
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="font-[inherit] leading-relaxed"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {words(text)} words (aim for 200–300 in the body) · blank line = new paragraph
            </span>
            <div className="flex flex-wrap gap-2">
              <CopyButton text={text} label="Copy letter" />
              <Button
                variant="outline"
                disabled={!dirty || save.isPending}
                onClick={() => save.mutate({ letterId: letter.id, changes: { content_md: text } })}
              >
                Save and update PDF
              </Button>
              <Button
                disabled={save.isPending}
                onClick={() =>
                  save.mutate({
                    letterId: letter.id,
                    changes: {
                      ...(dirty ? { content_md: text } : {}),
                      status: final ? 'draft' : 'final',
                    },
                  })
                }
              >
                <CircleCheck />
                {final ? 'Back to draft' : 'Mark as final'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  )
}
