import { LoaderCircle, Send } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'

import { useApplicationEmail, useContacts, useDraftEmail, useGmailStatus } from '../hooks'
import { EmailEditor } from './EmailEditor'

// The email can be (re)written while the application has not gone out.
const DRAFTABLE = ['ready_to_apply', 'waiting_for_approval', 'rejected_by_user', 'failed']

/** Application page, email channel: recipient → AI draft → review → approve. */
export function ApplicationEmailCard({ application }) {
  const gmail = useGmailStatus().data
  const email = useApplicationEmail(application.id)
  const contacts = useContacts({ approval: 'approved', page_size: 200 }).data?.items ?? []
  const draft = useDraftEmail(application.id)
  const [contactId, setContactId] = useState('')
  // This job's contacts first.
  const options = [...contacts].sort(
    (a, b) => (b.job?.id === application.job.id) - (a.job?.id === application.job.id),
  )
  const chosen = contactId || application.contact?.id || options[0]?.id || ''
  const current = email.data
  const canDraft =
    DRAFTABLE.includes(application.status) &&
    (!current || ['draft', 'rejected', 'failed'].includes(current.status))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Send className="size-4 text-primary" aria-hidden="true" />
          Email
        </CardTitle>
        <CardDescription>
          Written by AI from your resume, sent from your Gmail only after you approve it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {gmail && !gmail.connected && (
          <p className="text-sm">
            <Link to="/settings" className="font-medium text-primary hover:underline">
              Connect Gmail in Settings
            </Link>{' '}
            to send this application.
          </p>
        )}

        {canDraft && (
          <div className="space-y-2 rounded-md border p-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email-contact">Send to</Label>
              <Select
                id="email-contact"
                value={chosen}
                onChange={(e) => setContactId(e.target.value)}
              >
                {options.length === 0 && <option value="">No approved contacts</option>}
                {options.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.email}
                    {c.name ? ` — ${c.name}` : ''}
                    {c.job?.id === application.job.id ? ' (this job)' : ''}
                  </option>
                ))}
              </Select>
              <p className="text-xs text-muted-foreground">
                Only approved contacts are listed.{' '}
                <Link to="/contacts" className="text-primary hover:underline">
                  Manage contacts
                </Link>
              </p>
            </div>
            <Button
              onClick={() => draft.start(chosen)}
              disabled={!chosen || draft.running || !gmail?.connected}
            >
              {draft.running && <LoaderCircle className="animate-spin" />}
              {current ? 'Write the email again' : 'Write email'}
            </Button>
            {draft.running && draft.task && (
              <ProgressBar value={draft.task.progress} status={draft.task.status} />
            )}
            {draft.task?.status === 'failed' && (
              <p role="alert" className="text-xs text-destructive">
                {draft.task.error}
              </p>
            )}
          </div>
        )}

        {email.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
        {current && <EmailEditor key={`${current.id}-${current.updated_at}`} email={current} />}
        {!current && !email.isPending && !canDraft && (
          <p className="text-sm text-muted-foreground">No email for this application.</p>
        )}
      </CardContent>
    </Card>
  )
}
