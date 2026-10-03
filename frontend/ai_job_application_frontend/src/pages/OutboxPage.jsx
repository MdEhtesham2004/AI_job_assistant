import { useState } from 'react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { OUTBOX_TABS } from '@/features/outreach/api'
import { AutomationCard } from '@/features/outreach/components/AutomationCard'
import { EmailEditor } from '@/features/outreach/components/EmailEditor'
import { useApproveBatch, useOutbox, useOutboxSummary } from '@/features/outreach/hooks'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

export default function OutboxPage() {
  const [tab, setTab] = useState('drafts')
  const statuses = OUTBOX_TABS.find((t) => t.key === tab).statuses
  const outbox = useOutbox({ status: statuses, page_size: 100 })
  const summary = useOutboxSummary().data
  const approve = useApproveBatch()
  const [selected, setSelected] = useState([])
  const items = outbox.data?.items ?? []
  const toggle = (id) =>
    setSelected((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]))

  return (
    <>
      <PageHeader
        title="Outbox"
        description="Application emails and follow-ups: review, approve, and follow scheduled and sent mail."
      />
      <AutomationCard />

      {summary && (
        <Card className="mb-4">
          <CardContent className="flex flex-wrap gap-x-6 gap-y-1 py-3 text-sm">
            <span>
              Gmail:{' '}
              {summary.gmail_connected ? (
                <span className="font-medium">{summary.gmail_email}</span>
              ) : (
                <Link to="/settings" className="font-medium text-primary hover:underline">
                  not connected
                </Link>
              )}
            </span>
            <span>
              Sent today:{' '}
              <span className="font-medium">
                {summary.sent_today} / {summary.daily_cap}
              </span>
            </span>
            <span>At least {summary.interval_seconds}s between emails</span>
            {summary.next_slot && <span>Next free slot: {formatDateTime(summary.next_slot)}</span>}
          </CardContent>
        </Card>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border" role="tablist" aria-label="Outbox">
          {OUTBOX_TABS.map((t) => {
            const count = summary
              ? t.statuses.reduce((sum, s) => sum + (summary.counts[s] ?? 0), 0)
              : null
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => {
                  setTab(t.key)
                  setSelected([])
                }}
                className={cn(
                  'px-3 py-1.5 text-sm',
                  tab === t.key ? 'bg-primary text-primary-foreground' : 'hover:bg-accent',
                )}
              >
                {t.label}
                {count !== null && <span className="ml-1.5 text-xs opacity-75">{count}</span>}
              </button>
            )
          })}
        </div>
        {tab === 'drafts' && items.length > 0 && (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                setSelected(selected.length === items.length ? [] : items.map((e) => e.id))
              }
            >
              {selected.length === items.length ? 'Clear selection' : 'Select all'}
            </Button>
            <Button
              size="sm"
              disabled={selected.length === 0 || approve.isPending}
              onClick={() =>
                // Each card shows the contact's evidence, so this approves new contacts too.
                approve.mutate(
                  { ids: selected, approveContacts: true },
                  { onSuccess: () => setSelected([]) },
                )
              }
            >
              Approve selected ({selected.length})
            </Button>
          </>
        )}
      </div>

      {approve.data && Object.keys(approve.data.errors).length > 0 && (
        <div role="alert" className="mb-4 rounded-md border border-destructive/40 p-3 text-sm">
          <p className="font-medium text-destructive">Some emails were not approved:</p>
          <ul className="list-disc pl-5">
            {Object.entries(approve.data.errors).map(([id, message]) => (
              <li key={id}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      {outbox.isPending && <p className="text-muted-foreground">Loading…</p>}
      {outbox.isSuccess && items.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            {tab === 'drafts'
              ? 'No drafts. Open an email application and use "Write email".'
              : 'Nothing here.'}
          </CardContent>
        </Card>
      )}
      <ul className="space-y-4">
        {items.map((email) => (
          <li key={email.id}>
            <Card>
              <CardContent className="space-y-3 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="flex items-center gap-2 text-sm font-medium">
                    {tab === 'drafts' && (
                      <input
                        type="checkbox"
                        className="size-4 accent-primary"
                        checked={selected.includes(email.id)}
                        onChange={() => toggle(email.id)}
                        aria-label={`Select email to ${email.to_address}`}
                      />
                    )}
                    <Link
                      to={`/applications/${email.application.id}`}
                      className="hover:text-primary hover:underline"
                    >
                      {email.application.job_title} — {email.application.company}
                    </Link>
                  </label>
                </div>
                <EmailEditor key={`${email.id}-${email.updated_at}`} email={email} />
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </>
  )
}
