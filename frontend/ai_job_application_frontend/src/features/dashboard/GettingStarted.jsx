import { CheckCircle2, Circle, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const HIDDEN_KEY = 'getting-started-hidden'

const STEPS = [
  { key: 'resume', label: 'Upload your resume', to: '/resumes', action: 'Upload' },
  { key: 'jobs', label: 'Find jobs', to: '/jobs/search', action: 'Search' },
  { key: 'scored', label: 'Score a job against your resume', to: '/jobs', action: 'Open jobs' },
  {
    key: 'application',
    label: 'Prepare your first application',
    to: '/jobs',
    action: 'Pick a job',
  },
  {
    key: 'gmail',
    label: 'Connect Gmail to send applications by email',
    to: '/settings',
    action: 'Connect',
    optional: true,
  },
]

function readHidden() {
  try {
    return localStorage.getItem(HIDDEN_KEY) === '1'
  } catch {
    return false
  }
}

/** Phase 18: a guided first day. Disappears when the steps are done or when hidden. */
export function GettingStarted({ done = {} }) {
  const [hidden, setHidden] = useState(readHidden)
  const required = STEPS.filter((s) => !s.optional)
  const finished = required.filter((s) => done[s.key]).length
  if (hidden || finished === required.length) return null

  const hide = () => {
    try {
      localStorage.setItem(HIDDEN_KEY, '1')
    } catch {
      // private window: hide for this visit only
    }
    setHidden(true)
  }
  const next = STEPS.find((s) => !done[s.key])

  return (
    <Card className="border-primary/40">
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle>Getting started</CardTitle>
          <CardDescription>
            {finished} of {required.length} steps done — about 10 minutes in total.
          </CardDescription>
        </div>
        <Button variant="ghost" size="icon" onClick={hide} aria-label="Hide getting started">
          <X />
        </Button>
      </CardHeader>
      <CardContent>
        <ol className="space-y-2" aria-label="Getting started steps">
          {STEPS.map((step) => {
            const isDone = Boolean(done[step.key])
            return (
              <li key={step.key} className="flex items-center gap-3 text-sm">
                {isDone ? (
                  <CheckCircle2 className="size-5 shrink-0 text-success" aria-label="Done" />
                ) : (
                  <Circle className="size-5 shrink-0 text-muted-foreground" aria-label="To do" />
                )}
                <span className={isDone ? 'flex-1 text-muted-foreground line-through' : 'flex-1'}>
                  {step.label}
                  {step.optional && <span className="text-muted-foreground"> (optional)</span>}
                </span>
                {!isDone && (
                  <Link
                    to={step.to}
                    className={
                      step === next
                        ? 'inline-flex h-8 items-center rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90'
                        : 'text-xs font-medium text-primary hover:underline'
                    }
                  >
                    {step.action}
                  </Link>
                )}
              </li>
            )
          })}
        </ol>
      </CardContent>
    </Card>
  )
}
