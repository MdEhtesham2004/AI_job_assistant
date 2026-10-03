import { AlertTriangle, Paperclip } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { formatBytes, formatDateTime } from '@/lib/format'

import { useEditEmail, useEmailAction } from '../hooks'
import { EmailStatusBadge } from './Badges'

/** One application email: preview / edit while a draft, then its send state. */
export function EmailEditor({ email }) {
  const edit = useEditEmail()
  const action = useEmailAction()
  const [subject, setSubject] = useState(email.subject)
  const [body, setBody] = useState(email.body_text)
  const isDraft = email.status === 'draft'
  const dirty = subject !== email.subject || body !== email.body_text
  const busy = edit.isPending || action.isPending
  const act = (name) => action.mutate({ id: email.id, action: name })

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <EmailStatusBadge status={email.status} />
        <span className="text-muted-foreground">
          From {email.from_address} → <span className="text-foreground">{email.to_address}</span>
          {email.contact?.name ? ` (${email.contact.name})` : ''}
        </span>
      </div>

      {isDraft ? (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`subject-${email.id}`}>Subject</Label>
            <Input
              id={`subject-${email.id}`}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`body-${email.id}`}>Email</Label>
            <Textarea
              id={`body-${email.id}`}
              rows={14}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="font-mono text-[13px] leading-relaxed"
            />
          </div>
        </>
      ) : (
        <div className="rounded-md border bg-muted/30 p-3">
          <p className="mb-2 font-medium">{email.subject}</p>
          <p className="whitespace-pre-wrap leading-relaxed">{email.body_text}</p>
        </div>
      )}

      <ul className="flex flex-wrap gap-2" aria-label="Attachments">
        {email.attachments.map((file) => (
          <li key={file.id}>
            <a
              href={file.download_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs hover:bg-accent"
            >
              <Paperclip className="size-3.5" aria-hidden="true" />
              {file.file_name}
              {file.file_size > 0 && (
                <span className="text-muted-foreground">{formatBytes(file.file_size)}</span>
              )}
            </a>
          </li>
        ))}
      </ul>

      {isDraft && email.warnings.length > 0 && (
        <div role="alert" className="rounded-md border border-warning/40 bg-warning/10 p-3">
          <p className="mb-1 flex items-center gap-1.5 font-medium text-warning">
            <AlertTriangle className="size-4" aria-hidden="true" />
            Check before approving
          </p>
          <ul className="list-disc pl-5 text-xs">
            {email.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {email.status === 'queued' && (
        <p className="text-muted-foreground">
          Scheduled for{' '}
          <span className="font-medium text-foreground">{formatDateTime(email.scheduled_for)}</span>{' '}
          (send limits and gaps are respected).
        </p>
      )}
      {email.status === 'sending' && <p className="text-muted-foreground">Sending…</p>}
      {email.status === 'sent' && (
        <p className="text-success">Sent {formatDateTime(email.sent_at)} from Gmail.</p>
      )}
      {email.status === 'failed' && (
        <p role="alert" className="text-destructive">
          Not sent: {email.error}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {isDraft && (
          <>
            <Button
              variant="outline"
              disabled={!dirty || busy}
              onClick={() => edit.mutate({ id: email.id, changes: { subject, body_text: body } })}
            >
              Save changes
            </Button>
            <Button disabled={dirty || busy} onClick={() => act('approve')}>
              Approve &amp; send
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => act('reject')}>
              Reject
            </Button>
            {dirty && (
              <span className="self-center text-xs text-muted-foreground">
                Save your changes before approving.
              </span>
            )}
          </>
        )}
        {email.status === 'queued' && (
          <Button variant="outline" disabled={busy} onClick={() => act('cancel')}>
            Cancel sending
          </Button>
        )}
        {email.status === 'failed' && (
          <Button variant="outline" disabled={busy} onClick={() => act('retry')}>
            Back to draft
          </Button>
        )}
      </div>
    </div>
  )
}
