import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

import { MOVE_LABELS, STATUS_LABELS } from '../api'
import { useMarkApplied, useMoveApplication } from '../hooks'

const QUIET = new Set(['withdrawn', 'rejected', 'rejected_by_user'])

/** Only the moves the server allows (`allowed_next`); each asks for an optional note. */
export function MoveButtons({ application, size = 'sm' }) {
  const move = useMoveApplication()
  const markApplied = useMarkApplied()
  const [target, setTarget] = useState(null)
  const [note, setNote] = useState('')
  const busy = move.isPending || markApplied.isPending

  if (!application.allowed_next.length) {
    return <p className="text-sm text-muted-foreground">Final status — no further steps.</p>
  }

  const confirm = () => {
    const done = { onSuccess: () => setTarget(null) }
    if (target === 'applied' && application.channel !== 'email') {
      markApplied.mutate({ id: application.id, note }, done)
    } else {
      move.mutate({ id: application.id, toStatus: target, note }, done)
    }
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {application.allowed_next.map((status) => (
          <Button
            key={status}
            size={size}
            variant={QUIET.has(status) ? 'outline' : 'default'}
            onClick={() => {
              setNote('')
              setTarget(status)
            }}
            disabled={busy}
          >
            {MOVE_LABELS[status] ?? STATUS_LABELS[status]}
          </Button>
        ))}
      </div>
      <Dialog
        open={Boolean(target)}
        onClose={() => setTarget(null)}
        title={`Move to “${STATUS_LABELS[target] ?? ''}”`}
        description="Add a note for your timeline (optional)."
      >
        <Textarea
          aria-label="Note"
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. Interview on Monday 10:00 with the tech lead"
        />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setTarget(null)}>
            Cancel
          </Button>
          <Button onClick={confirm} disabled={busy}>
            Confirm
          </Button>
        </div>
      </Dialog>
    </>
  )
}
