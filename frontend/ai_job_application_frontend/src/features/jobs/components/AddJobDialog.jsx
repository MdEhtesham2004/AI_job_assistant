import { ClipboardPaste, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { FormError } from '@/components/common/FormError'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { isActive } from '@/features/tasks/api'
import { useTaskPolling } from '@/features/tasks/hooks'

import { useScanText } from '../hooks'

const MIN_DESCRIPTION = 200

/**
 * "Add a job" (Phase 18, was the Scan page): paste a job found anywhere — it is saved as a
 * private job (only you see it) and scored, then opened.
 */
export function AddJobDialog() {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [description, setDescription] = useState('')
  const scan = useScanText()
  const navigate = useNavigate()
  const started = scan.data
  const task = useTaskPolling(started?.task_id ?? null).data
  const scoring = scan.isPending || (task && isActive(task))

  useEffect(() => {
    if (started && task && !isActive(task)) {
      // Scored (or scoring failed — the job is saved either way): open it. Leaving the
      // Jobs page also closes this dialog.
      navigate(`/jobs/${started.job_id}`)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once the task finishes
  }, [task?.status])

  const onSubmit = (event) => {
    event.preventDefault()
    scan.mutate({
      title: title.trim() || 'Pasted job',
      company: company.trim() || 'Unknown company',
      description: description.trim(),
    })
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <ClipboardPaste />
        Add a job
      </Button>
      <Dialog
        open={open}
        onClose={() => !scoring && setOpen(false)}
        title="Add a job"
        description="Found a job somewhere else? Paste it here. It is saved privately (only you see it) and scored against your resume."
        className="max-w-2xl"
      >
        <form onSubmit={onSubmit} className="space-y-3">
          <FormError message={scan.error?.message} />
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="add-title">Job title</Label>
              <Input id="add-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="add-company">Company</Label>
              <Input
                id="add-company"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-description">Job description</Label>
            <Textarea
              id="add-description"
              rows={10}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {description.trim().length < MIN_DESCRIPTION
                ? `At least ${MIN_DESCRIPTION} characters (${description.trim().length} so far).`
                : 'Ready.'}
            </p>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={scoring}>
              Cancel
            </Button>
            <Button type="submit" disabled={scoring || description.trim().length < MIN_DESCRIPTION}>
              {scoring && <LoaderCircle className="animate-spin" />}
              {scoring ? 'Saving and scoring…' : 'Add and score'}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  )
}
