import { Download, FileText, Pencil } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'

import { VERDICT } from '../api'
import { useEditTurn, useStartReport } from '../hooks'

function TurnLine({ interviewId, turn, editable }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(turn.text)
  const edit = useEditTurn(interviewId)
  const mine = turn.speaker === 'candidate'
  return (
    <li className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">
        {mine ? 'You' : 'Maya'}
        {turn.edited && ' · corrected'}
      </p>
      {editing ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault()
            edit.mutate({ seq: turn.seq, text }, { onSuccess: () => setEditing(false) })
          }}
        >
          <Textarea
            aria-label={`Correct answer ${turn.seq}`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
          />
          <div className="flex gap-2">
            <Button size="sm" type="submit" disabled={edit.isPending || !text.trim()}>
              Save
            </Button>
            <Button size="sm" type="button" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex items-start gap-2">
          <p className={mine ? 'text-sm' : 'text-sm text-muted-foreground'}>{turn.text}</p>
          {editable && mine && (
            <Button
              size="icon"
              variant="ghost"
              className="size-7 shrink-0"
              aria-label={`Correct answer ${turn.seq}`}
              onClick={() => setEditing(true)}
            >
              <Pencil className="size-3.5" />
            </Button>
          )}
        </div>
      )}
    </li>
  )
}

export function Transcript({ interview, editable }) {
  if (!interview.turns.length) {
    return <p className="text-sm text-muted-foreground">No transcript was recorded.</p>
  }
  return (
    <ol className="space-y-3">
      {interview.turns.map((turn) => (
        <TurnLine key={turn.seq} interviewId={interview.id} turn={turn} editable={editable} />
      ))}
    </ol>
  )
}

/** After the call: fix misheard words, then ask for the report. */
export function ReviewTranscript({ interview }) {
  const report = useStartReport(interview.id)
  const answered = interview.turns.some((t) => t.speaker === 'candidate' && t.text.trim())
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Transcript</CardTitle>
          <CardDescription>
            Speech recognition can mishear words. Correct your answers if needed — corrections are
            marked in the report.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Transcript interview={interview} editable />
        </CardContent>
      </Card>
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>Your report</CardTitle>
          <CardDescription>
            A score per question with quotes from your answers, a stronger example answer and a
            practice plan.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {interview.error && (
            <p role="alert" className="text-sm text-destructive">
              {interview.error}
            </p>
          )}
          {!answered && (
            <p className="text-sm text-muted-foreground">
              No answers were recorded, so there is nothing to assess.
            </p>
          )}
          <Button onClick={() => report.mutate()} disabled={!answered || report.isPending}>
            <FileText />
            Get my report
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

function Stars({ score }) {
  return (
    <span className="tabular-nums font-semibold" aria-label={`${score} out of 5`}>
      {score}/5
    </span>
  )
}

function List({ title, items }) {
  if (!items?.length) return null
  return (
    <div>
      <p className="text-sm font-medium">{title}</p>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

export function ReportView({ interview, actions }) {
  const { report } = interview
  const body = report.report
  const verdict = VERDICT[report.verdict]
  const m = body.metrics ?? {}
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 pt-6">
          <div>
            <p className="text-4xl font-semibold tabular-nums">{report.overall_score}</p>
            <p className="text-xs text-muted-foreground">out of 100</p>
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <Badge variant={verdict.variant}>{verdict.label}</Badge>
            <p className="text-sm">{body.summary}</p>
            <p className="text-xs text-muted-foreground">
              Based on a short interview with a few answers — treat the score as a rough signal and
              focus on the feedback below.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {report.pdf_url && (
              <Button variant="outline" onClick={() => window.open(report.pdf_url, '_blank')}>
                <Download />
                PDF
              </Button>
            )}
            {actions}
          </div>
        </CardContent>
      </Card>

      <section aria-label="Questions" className="flex flex-col gap-4">
        {body.questions.map((q) => (
          <Card key={q.question_id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-start justify-between gap-3 text-base">
                <span>{q.question}</span>
                <Stars score={q.score} />
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {q.quote ? (
                <blockquote className="border-l-2 pl-3 text-muted-foreground">
                  “{q.quote}”
                </blockquote>
              ) : (
                <p className="text-muted-foreground">No clear answer was recorded.</p>
              )}
              <p>
                <span className="font-medium">Went well:</span> {q.went_well}
              </p>
              <p>
                <span className="font-medium">Missing:</span> {q.missing}
              </p>
              <details>
                <summary className="cursor-pointer font-medium text-primary">
                  A stronger answer
                </summary>
                <p className="mt-1">{q.better_answer}</p>
              </details>
            </CardContent>
          </Card>
        ))}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Strengths and improvements</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <List title="Strengths" items={body.strengths} />
            <List title="To improve" items={body.improvements} />
            <List title="Job skills you showed" items={body.skills_shown} />
            <List title="Job skills not shown yet" items={body.skills_not_shown} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Communication</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <dl className="grid grid-cols-2 gap-2">
              <dt className="text-muted-foreground">Clarity</dt>
              <dd className="tabular-nums">{body.communication.clarity}/5</dd>
              <dt className="text-muted-foreground">Structure</dt>
              <dd className="tabular-nums">{body.communication.structure}/5</dd>
              <dt className="text-muted-foreground">Words per answer</dt>
              <dd className="tabular-nums">{m.average_answer_words ?? 0}</dd>
              <dt className="text-muted-foreground">Filler words</dt>
              <dd className="tabular-nums">
                {m.filler_words ?? 0}
                {m.top_fillers?.length > 0 && ` (${m.top_fillers.join(', ')})`}
              </dd>
            </dl>
            <p>{body.communication.notes}</p>
            <List title="Practice plan" items={body.practice_plan} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Transcript</CardTitle>
        </CardHeader>
        <CardContent>
          <Transcript interview={interview} editable={false} />
        </CardContent>
      </Card>
    </div>
  )
}
