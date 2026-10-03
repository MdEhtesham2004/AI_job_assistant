import { ClipboardList } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useJobDocuments } from '@/features/jobs/hooks'
import { useContacts } from '@/features/outreach/hooks'
import { KIND_LABELS } from '@/features/resumes/api'
import { useResumes } from '@/features/resumes/hooks'

import { CHANNEL_LABELS } from '../api'
import { useCreateApplication, useJobApplication } from '../hooks'
import { ApplicationStatusBadge } from './ApplicationStatusBadge'

/** Job page: the application for this job, or a form to prepare one. */
export function PrepareApplicationCard({ job }) {
  const existing = useJobApplication(job.id)
  if (existing.isPending) return null
  const application = existing.data

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardList className="size-4 text-primary" aria-hidden="true" />
          Application
        </CardTitle>
        {!application && (
          <CardDescription>Track this job as an application — one per job.</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        {application ? (
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <span className="flex items-center gap-2">
              <ApplicationStatusBadge status={application.status} />
              {CHANNEL_LABELS[application.channel]}
            </span>
            <Link
              to={`/applications/${application.id}`}
              className="font-medium text-primary hover:underline"
            >
              Open application
            </Link>
          </div>
        ) : (
          <PrepareForm job={job} />
        )}
      </CardContent>
    </Card>
  )
}

function PrepareForm({ job }) {
  const create = useCreateApplication()
  const docs = useJobDocuments(job.id).data
  const resumes = useResumes().data
  const tailored = docs?.tailored
  const versions = [
    ...(tailored
      ? [{ id: tailored.id, label: `v${tailored.version_no} · Tailored for this job` }]
      : []),
    ...(resumes?.versions ?? [])
      .filter((v) => v.parse_status === 'parsed' && v.kind !== 'tailored')
      .map((v) => ({
        id: v.id,
        label: `v${v.version_no} · ${KIND_LABELS[v.kind]}${v.is_active ? ' (active)' : ''}`,
      })),
  ]
  // A LinkedIn hiring post asks for an email; other jobs usually have an apply link.
  const [channel, setChannel] = useState(
    job.source === 'linkedin_post' || !job.apply_url ? 'email' : 'portal',
  )
  const [resumeId, setResumeId] = useState('')
  const [withLetter, setWithLetter] = useState(true)
  const [nextAction, setNextAction] = useState('')
  const chosenResume = resumeId || versions[0]?.id || ''
  // Approved contacts, this job's first (e.g. the address of a LinkedIn hiring post).
  const approved = useContacts({ approval: 'approved', page_size: 200 }).data?.items ?? []
  const contacts = [...approved].sort((a, b) => (b.job?.id === job.id) - (a.job?.id === job.id))
  const [contactId, setContactId] = useState('')
  const chosenContact = contactId || contacts[0]?.id || ''

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault()
        create.mutate({
          jobId: job.id,
          body: {
            channel,
            resume_version_id: chosenResume || null,
            cover_letter_id: withLetter && docs?.cover_letter ? docs.cover_letter.id : null,
            contact_id: channel === 'email' && chosenContact ? chosenContact : null,
            next_action: nextAction || null,
          },
        })
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="app-channel">How you apply</Label>
          <Select id="app-channel" value={channel} onChange={(e) => setChannel(e.target.value)}>
            {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="app-resume">Resume</Label>
          <Select
            id="app-resume"
            value={chosenResume}
            onChange={(e) => setResumeId(e.target.value)}
          >
            {versions.length === 0 && <option value="">No parsed resume</option>}
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </Select>
        </div>
      </div>
      {docs?.cover_letter && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            checked={withLetter}
            onChange={(e) => setWithLetter(e.target.checked)}
          />
          Attach the cover letter ({docs.cover_letter.status})
        </label>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="app-next">Next action (optional)</Label>
        <Input
          id="app-next"
          value={nextAction}
          onChange={(e) => setNextAction(e.target.value)}
          placeholder="e.g. Apply on the careers page by Friday"
        />
      </div>
      {channel === 'email' && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="app-contact">Send to</Label>
          <Select
            id="app-contact"
            value={chosenContact}
            onChange={(e) => setContactId(e.target.value)}
          >
            {contacts.length === 0 && <option value="">Choose later (no approved contacts)</option>}
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.email}
                {c.name ? ` — ${c.name}` : ''}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">
            You review and approve the email before Gmail sends it.{' '}
            <Link to="/contacts" className="text-primary hover:underline">
              Contacts
            </Link>
          </p>
        </div>
      )}
      <Button type="submit" disabled={create.isPending}>
        Prepare application
      </Button>
    </form>
  )
}
