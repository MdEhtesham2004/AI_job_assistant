import { Check, ClipboardList, Copy, LoaderCircle, Pencil, Plus } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

import { FILL_IN, useAnswers, useEditAnswer, useMakeAnswers } from '../api'

function Highlighted({ text }) {
  const parts = text.split(FILL_IN)
  return parts.map((part, i) => (
    <span key={i}>
      {part}
      {i < parts.length - 1 && (
        <mark className="rounded bg-warning/20 px-1 text-warning">{FILL_IN}</mark>
      )}
    </span>
  ))
}

function AnswerItem({ jobId, item }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(item.answer)
  const [copied, setCopied] = useState(false)
  const edit = useEditAnswer(jobId)
  const needsFill = item.answer.includes(FILL_IN)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(item.answer)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('Copy failed — select the text instead.')
    }
  }

  return (
    <li className="space-y-1.5 border-t pt-3 first:border-t-0 first:pt-0">
      <p className="text-sm font-medium">{item.question}</p>
      {editing ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault()
            edit.mutate({ key: item.key, answer: text }, { onSuccess: () => setEditing(false) })
          }}
        >
          <Textarea
            aria-label={`Edit answer: ${item.question}`}
            value={text}
            rows={4}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex gap-2">
            <Button size="sm" type="submit" disabled={!text.trim() || edit.isPending}>
              Save
            </Button>
            <Button size="sm" type="button" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <p className="whitespace-pre-line text-sm text-muted-foreground">
          <Highlighted text={item.answer} />
        </p>
      )}
      {item.check?.length > 0 && !item.edited && (
        <p className="text-xs text-warning">
          Check these numbers — they are not in your resume: {item.check.join(', ')}
        </p>
      )}
      {!editing && (
        <div className="flex gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={copy}
            disabled={needsFill}
            title={needsFill ? 'Fill in the marked part first' : undefined}
            aria-label={`Copy answer: ${item.question}`}
          >
            {copied ? <Check /> : <Copy />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setText(item.answer)
              setEditing(true)
            }}
            aria-label={`Edit answer: ${item.question}`}
          >
            <Pencil />
            Edit
          </Button>
          {item.edited && <span className="self-center text-xs text-muted-foreground">edited</span>}
        </div>
      )}
    </li>
  )
}

/** Job page: ready-to-paste answers to common application-form questions. */
export function ScreeningAnswersCard({ job }) {
  const answers = useAnswers(job.id)
  const data = answers.data
  const make = useMakeAnswers(job.id, data?.running_task_id)
  const [questions, setQuestions] = useState([])
  const [draft, setDraft] = useState('')
  const items = data?.answers ?? []
  const usable = job.description_quality !== 'missing'

  const addQuestion = () => {
    const q = draft.trim()
    if (!q || questions.length >= 3) return
    setQuestions((list) => [...list, q])
    setDraft('')
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardList className="size-4 text-primary" aria-hidden="true" />
          Screening answers
        </CardTitle>
        <CardDescription>
          Answers to common application-form questions, written from your resume for this job.
          Notice period and salary come from your Profile — never guessed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {items.length > 0 && (
          <ol className="space-y-3">
            {items.map((item) => (
              <AnswerItem key={`${item.key}-${data.updated_at}`} jobId={job.id} item={item} />
            ))}
          </ol>
        )}
        {usable ? (
          <div className="space-y-2">
            <div className="flex gap-2">
              <Input
                aria-label="Add your own question"
                placeholder="Add a question from the form (optional)"
                value={draft}
                maxLength={300}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addQuestion()
                  }
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label="Add question"
                onClick={addQuestion}
                disabled={!draft.trim() || questions.length >= 3}
              >
                <Plus />
              </Button>
            </div>
            {questions.length > 0 && (
              <ul className="list-disc pl-5 text-xs text-muted-foreground">
                {questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            )}
            <Button onClick={() => make.start(questions)} disabled={make.running}>
              {make.running && <LoaderCircle className="animate-spin" />}
              {make.running
                ? 'Writing answers…'
                : items.length
                  ? 'Rewrite answers (keeps your edits)'
                  : 'Write my answers'}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Paste the job description first.</p>
        )}
      </CardContent>
    </Card>
  )
}
