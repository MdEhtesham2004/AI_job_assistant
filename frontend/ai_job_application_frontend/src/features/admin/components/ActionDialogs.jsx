import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onClose,
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title} description={description}>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button variant={danger ? 'destructive' : 'default'} onClick={onConfirm} disabled={busy}>
          {busy ? 'Working…' : confirmLabel}
        </Button>
      </div>
    </Dialog>
  )
}

export function RejectDialog({ open, user, busy, onConfirm, onClose }) {
  const [reason, setReason] = useState('')
  const close = () => {
    setReason('')
    onClose()
  }
  return (
    <Dialog
      open={open}
      onClose={close}
      title={`Reject ${user?.full_name ?? 'account'}?`}
      description="The person will not be able to sign in. You can still approve the account later."
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault()
          onConfirm(reason.trim())
          setReason('')
        }}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="reject-reason">Reason (optional, internal)</Label>
          <Textarea
            id="reject-reason"
            maxLength={500}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. Not part of the pilot group"
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={close} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant="destructive" disabled={busy}>
            {busy ? 'Rejecting…' : 'Reject'}
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
