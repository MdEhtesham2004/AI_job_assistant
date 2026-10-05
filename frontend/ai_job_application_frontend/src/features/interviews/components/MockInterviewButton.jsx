import { Mic } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useUsage } from '@/features/dashboard/api'

import { DIFFICULTY_OPTIONS, ROUND_OPTIONS, guessDifficulty } from '../api'
import { useCreateInterview } from '../hooks'

/** "Mock interview" on a job or application: choose the round, then the AI plans it. */
export function MockInterviewButton({ job, variant = 'outline', retryOf = null, label }) {
  const [open, setOpen] = useState(false)
  const [round, setRound] = useState('mixed')
  const [difficulty, setDifficulty] = useState(() => guessDifficulty(job))
  const create = useCreateInterview(job.id)
  const navigate = useNavigate()
  const usage = useUsage().data
  const quota = usage?.interviews_month
  const minutes = usage?.interview_minutes ?? 6
  const noneLeft = quota?.limit > 0 && quota.left === 0
  const unavailable = usage && usage.interviews_available === false

  const begin = async (body) => {
    const created = await create.mutateAsync(body)
    setOpen(false)
    navigate(`/interviews/${created.interview_id}`)
  }

  if (retryOf) {
    return (
      <Button
        variant={variant}
        disabled={create.isPending || noneLeft}
        onClick={() =>
          begin({ retry_of_id: retryOf.id, round: retryOf.round, difficulty: retryOf.difficulty })
        }
      >
        <Mic />
        {label ?? 'Retry weak questions'}
      </Button>
    )
  }

  return (
    <>
      <Button variant={variant} onClick={() => setOpen(true)}>
        <Mic />
        {label ?? 'Mock interview'}
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Mock interview"
        description={`A ${minutes}-minute voice screen with Maya, a friendly AI interviewer, based on this job and your resume. You get a detailed report afterwards.`}
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            begin({ round, difficulty })
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="interview-round">Round</Label>
            <Select id="interview-round" value={round} onChange={(e) => setRound(e.target.value)}>
              {ROUND_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="interview-difficulty">Level</Label>
            <Select
              id="interview-difficulty"
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
            >
              {DIFFICULTY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </div>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            <li>English only. Use headphones in a quiet room for the best result.</li>
            <li>
              Your voice goes to OpenAI to run the interview; we keep only the text transcript.
            </li>
            {quota?.limit > 0 && (
              <li>
                {quota.left} of {quota.limit} interviews left this month (practising again counts
                too).
              </li>
            )}
          </ul>
          {unavailable && (
            <p role="alert" className="text-sm text-destructive">
              Mock interviews are not set up yet (the admin needs to add an OpenAI key).
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || noneLeft || unavailable}>
              {create.isPending ? 'Preparing…' : 'Prepare interview'}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  )
}
