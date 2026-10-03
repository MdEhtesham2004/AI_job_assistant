import { useQueryClient } from '@tanstack/react-query'
import {
  Ban,
  Check,
  Download,
  ExternalLink,
  LoaderCircle,
  Mail,
  RefreshCw,
  Search,
  Trash2,
  UserPlus,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'

import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useSettings } from '@/features/account/hooks'
import { applicationsApi } from '@/features/applications/api'
import { SOURCE_LABELS } from '@/features/outreach/api'
import { ApprovalBadge, VerificationBadge } from '@/features/outreach/components/Badges'
import {
  useBlock,
  useBlocked,
  useContactCounts,
  useContacts,
  useCreateContact,
  useDeleteContact,
  useDiscoverContacts,
  useExportContacts,
  useUnblock,
  useUpdateContact,
  useVerifyContact,
} from '@/features/outreach/hooks'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

const TABS = [
  { key: 'pending', label: 'Needs approval' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: '', label: 'All' },
]

export default function ContactsPage() {
  const [params, setParams] = useSearchParams()
  const approval = params.get('approval') ?? 'pending'
  const [q, setQ] = useState('')
  const [adding, setAdding] = useState(false)
  const contacts = useContacts({ approval, q, page_size: 100 })
  const counts = useContactCounts().data
  const exporter = useExportContacts()

  return (
    <>
      <PageHeader
        title="Contacts"
        description="People you may email. Every contact needs your approval and shows where it came from."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => exporter.mutate({ approval, q })}
              disabled={exporter.isPending}
              title="Contacts in this tab and search, with company, role, date posted and description"
            >
              <Download />
              Export CSV
            </Button>
            <Button onClick={() => setAdding(true)}>
              <UserPlus />
              Add contact
            </Button>
          </>
        }
      />
      <AddContactDialog open={adding} onClose={() => setAdding(false)} />

      <div className="flex flex-col gap-6">
        <LinkedInSearch />

        <section aria-label="Contacts" className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-md border" role="tablist" aria-label="Approval">
              {TABS.map((tab) => (
                <button
                  key={tab.key || 'all'}
                  type="button"
                  role="tab"
                  aria-selected={approval === tab.key}
                  onClick={() => setParams(tab.key ? { approval: tab.key } : { approval: '' })}
                  className={cn(
                    'px-3 py-1.5 text-sm',
                    approval === tab.key ? 'bg-primary text-primary-foreground' : 'hover:bg-accent',
                  )}
                >
                  {tab.label}
                  {counts && (
                    <span className="ml-1.5 text-xs opacity-75">
                      {tab.key ? counts.counts[tab.key] : counts.total}
                    </span>
                  )}
                </button>
              ))}
            </div>
            <Input
              className="max-w-xs"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Email, name, company or job"
              aria-label="Search contacts"
            />
          </div>
          {contacts.isPending && <p className="text-muted-foreground">Loading…</p>}
          {contacts.data?.items.length === 0 && (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                {approval === 'pending' ? 'Nothing waiting for approval.' : 'No contacts here yet.'}
              </CardContent>
            </Card>
          )}
          <ul className="space-y-2">
            {contacts.data?.items.map((contact) => (
              <ContactRow key={contact.id} contact={contact} />
            ))}
          </ul>
        </section>

        <DoNotContact />
      </div>
    </>
  )
}

function LinkedInSearch() {
  const settings = useSettings().data
  const discover = useDiscoverContacts()
  const [keyword, setKeyword] = useState('')
  const [postedLimit, setPostedLimit] = useState('week')
  const [maxPosts, setMaxPosts] = useState(50)
  const enabled = settings?.linkedin_source_enabled
  const result = discover.task?.status === 'succeeded' ? discover.task.result : null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Find hiring posts on LinkedIn</CardTitle>
        <CardDescription>
          Public posts that say &quot;Hiring&quot;, name the role and publish a gmail.com address.
          Each post becomes a job you can score and apply to; its address waits here for your
          approval.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {settings && !enabled && (
          <p className="text-sm">
            This source is off.{' '}
            <Link to="/settings" className="font-medium text-primary hover:underline">
              Turn on &quot;LinkedIn hiring posts&quot; in Settings
            </Link>{' '}
            to use it.
          </p>
        )}
        <form
          className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_auto]"
          onSubmit={(event) => {
            event.preventDefault()
            discover.start({ keyword, posted_limit: postedLimit, max_posts: Number(maxPosts) })
          }}
        >
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Role or skill, e.g. React Native"
            aria-label="Role or skill"
            disabled={!enabled}
          />
          <Select
            aria-label="Posted within"
            value={postedLimit}
            onChange={(e) => setPostedLimit(e.target.value)}
            disabled={!enabled}
          >
            <option value="24h">Last 24 hours</option>
            <option value="week">Last week</option>
            <option value="month">Last month</option>
          </Select>
          <Select
            aria-label="Posts to read"
            value={maxPosts}
            onChange={(e) => setMaxPosts(e.target.value)}
            disabled={!enabled}
          >
            {[20, 50, 100].map((n) => (
              <option key={n} value={n}>
                {n} posts
              </option>
            ))}
          </Select>
          <Button
            type="submit"
            disabled={!enabled || keyword.trim().length < 2 || discover.running}
          >
            {discover.running ? <LoaderCircle className="animate-spin" /> : <Search />}
            Search
          </Button>
        </form>
        {discover.running && discover.task && (
          <div className="space-y-1">
            <ProgressBar value={discover.task.progress} status={discover.task.status} />
            <p className="text-xs text-muted-foreground">
              Reading posts on Apify and checking each one — this takes a minute or two.
            </p>
          </div>
        )}
        {discover.task?.status === 'failed' && (
          <p role="alert" className="text-sm text-destructive">
            {discover.task.error}
          </p>
        )}
        {result && (
          <p className="text-sm">
            {result.posts} posts read · {result.jobs} hiring posts with an email ·{' '}
            <span className="font-medium">{result.new_contacts} new contacts</span>
            {result.known_contacts > 0 && ` · ${result.known_contacts} already known`}
            {result.blocked > 0 && ` · ${result.blocked} on do-not-contact`}
            {result.not_hiring > 0 && ` · ${result.not_hiring} not hiring posts`}
            {result.stopped && <span className="text-warning"> · stopped: {result.stopped}</span>}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/** Approved contact → its job's email application (created if needed) → write & approve. */
function EmailApplicationButton({ contact }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const open = async () => {
    setBusy(true)
    try {
      const created = await applicationsApi.create(contact.job.id, {
        channel: 'email',
        contact_id: contact.id,
      })
      queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() })
      navigate(`/applications/${created.id}`)
    } catch (error) {
      // One application per job: open the one that exists.
      if (error?.code === 'APPLICATION_EXISTS') {
        navigate(`/applications/${error.details.application_id}`)
      } else {
        toast.error(error.message)
      }
    } finally {
      setBusy(false)
    }
  }
  return (
    <Button size="sm" onClick={open} disabled={busy}>
      {busy ? <LoaderCircle className="animate-spin" /> : <Mail />}
      Email application
    </Button>
  )
}

function ContactRow({ contact }) {
  const update = useUpdateContact()
  const verify = useVerifyContact()
  const remove = useDeleteContact()
  const block = useBlock()
  const busy = update.isPending || verify.isPending || remove.isPending || block.isPending
  const setApproval = (approval) => update.mutate({ id: contact.id, changes: { approval } })

  return (
    <li className="rounded-lg border bg-card p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{contact.email}</span>
            <ApprovalBadge value={contact.approval} />
            <VerificationBadge value={contact.verification} />
            {contact.blocked && <Badge variant="destructive">Do not contact</Badge>}
          </p>
          <p className="text-muted-foreground">
            {[contact.name, contact.role_title].filter(Boolean).join(' · ') || 'No name'}
          </p>
          {contact.job && (
            <p>
              For{' '}
              <Link to={`/jobs/${contact.job.id}`} className="text-primary hover:underline">
                {contact.job.title} — {contact.job.company}
              </Link>
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {contact.approval === 'approved' && contact.job && !contact.blocked && (
            <EmailApplicationButton contact={contact} />
          )}
          {contact.approval !== 'approved' && (
            <Button
              size="sm"
              onClick={() => setApproval('approved')}
              disabled={busy || contact.verification === 'invalid' || contact.blocked}
            >
              <Check />
              Approve
            </Button>
          )}
          {contact.approval !== 'rejected' && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setApproval('rejected')}
              disabled={busy}
            >
              <X />
              Reject
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => verify.mutate(contact.id)}
            disabled={busy}
            aria-label={`Check ${contact.email} again`}
          >
            <RefreshCw />
          </Button>
          {!contact.blocked && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                block.mutate({ email: contact.email, reason: 'Blocked from Contacts' })
              }
              disabled={busy}
              aria-label={`Never contact ${contact.email}`}
            >
              <Ban />
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => remove.mutate(contact.id)}
            disabled={busy}
            aria-label={`Delete ${contact.email}`}
          >
            <Trash2 />
          </Button>
        </div>
      </div>
      <div className="mt-2 rounded-md bg-muted/40 p-2 text-xs">
        <p className="mb-1 flex flex-wrap items-center gap-2 text-muted-foreground">
          <span>Source: {SOURCE_LABELS[contact.source] ?? contact.source}</span>
          <span>· found {formatRelative(contact.created_at)}</span>
          {contact.source_url && (
            <a
              href={contact.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              View post <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          )}
        </p>
        {contact.source_excerpt && (
          <blockquote className="italic">{contact.source_excerpt}</blockquote>
        )}
      </div>
    </li>
  )
}

function AddContactDialog({ open, onClose }) {
  const create = useCreateContact()
  const [values, setValues] = useState({ email: '', name: '', role_title: '', company: '' })
  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }))

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a contact"
      description="Someone you know or an address from a job posting. Added contacts are approved straight away."
    >
      <form
        className="space-y-3"
        onSubmit={async (event) => {
          event.preventDefault()
          try {
            await create.mutateAsync(values)
            setValues({ email: '', name: '', role_title: '', company: '' })
            onClose()
          } catch {
            // the toast shows the reason
          }
        }}
      >
        {[
          ['email', 'Email', 'hr@company.com'],
          ['name', 'Name (optional)', 'Priya Sharma'],
          ['role_title', 'Role (optional)', 'HR Manager'],
          ['company', 'Company (optional)', 'ABC Technologies'],
        ].map(([key, label, placeholder]) => (
          <div key={key} className="flex flex-col gap-1.5">
            <Label htmlFor={`contact-${key}`}>{label}</Label>
            <Input
              id={`contact-${key}`}
              type={key === 'email' ? 'email' : 'text'}
              required={key === 'email'}
              value={values[key]}
              onChange={set(key)}
              placeholder={placeholder}
            />
          </div>
        ))}
        <Button type="submit" disabled={create.isPending}>
          Add contact
        </Button>
      </form>
    </Dialog>
  )
}

function DoNotContact() {
  const entries = useBlocked().data ?? []
  const block = useBlock()
  const unblock = useUnblock()
  const [target, setTarget] = useState('')

  return (
    <Card>
      <CardHeader>
        <CardTitle>Do not contact</CardTitle>
        <CardDescription>
          Addresses and whole domains that are never emailed, even if a contact was approved.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            const value = target.trim()
            block.mutate(
              value.includes('@') && !value.startsWith('@') ? { email: value } : { domain: value },
              {
                onSuccess: () => setTarget(''),
              },
            )
          }}
        >
          <Input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="person@company.com or company.com"
            aria-label="Email or domain"
          />
          <Button type="submit" variant="outline" disabled={!target.trim() || block.isPending}>
            Add
          </Button>
        </form>
        {entries.length === 0 ? (
          <p className="text-muted-foreground">Nobody on the list.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {entries.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between gap-2 px-3 py-2">
                <span>
                  <span className="font-medium">{entry.email ?? `*@${entry.domain}`}</span>
                  {entry.reason && <span className="text-muted-foreground"> · {entry.reason}</span>}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => unblock.mutate(entry.id)}
                  aria-label={`Remove ${entry.email ?? entry.domain}`}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
