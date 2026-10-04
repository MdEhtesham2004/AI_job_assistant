import { CheckCheck } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select } from '@/components/ui/select'
import { useMarkAllRead, useMarkRead, useNotificationPage } from '@/features/notifications/hooks'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

const CATEGORIES = [
  ['', 'Everything'],
  ['email', 'Emails & Gmail'],
  ['replies', 'Replies'],
  ['jobs', 'Jobs & automation'],
  ['tasks', 'Background tasks'],
  ['other', 'Other'],
]
const SEVERITY = { success: 'success', warning: 'warning', error: 'destructive', info: 'outline' }

export default function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(1)
  const list = useNotificationPage({ unreadOnly, category, page })
  const markRead = useMarkRead()
  const markAll = useMarkAllRead()
  const data = list.data
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Everything the platform told you: emails, replies, automation runs and tasks."
        actions={
          <Button variant="outline" onClick={() => markAll.mutate()} disabled={markAll.isPending}>
            <CheckCheck />
            Mark all as read
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border" role="tablist" aria-label="Read state">
          {[
            [false, 'All'],
            [true, 'Unread'],
          ].map(([value, label]) => (
            <button
              key={label}
              type="button"
              role="tab"
              aria-selected={unreadOnly === value}
              onClick={() => {
                setUnreadOnly(value)
                setPage(1)
              }}
              className={cn(
                'px-3 py-1.5 text-sm',
                unreadOnly === value ? 'bg-primary text-primary-foreground' : 'hover:bg-accent',
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <Select
          className="max-w-56"
          aria-label="Kind"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value)
            setPage(1)
          }}
        >
          {CATEGORIES.map(([value, label]) => (
            <option key={value || 'all'} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      {list.isPending && <p className="text-muted-foreground">Loading…</p>}
      {data?.items.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Nothing here.
          </CardContent>
        </Card>
      )}
      <ul className="space-y-2">
        {data?.items.map((n) => (
          <li
            key={n.id}
            className={cn(
              'flex flex-wrap items-start justify-between gap-3 rounded-lg border bg-card p-3 text-sm',
              !n.read_at && 'border-primary/40',
            )}
          >
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2">
                {!n.read_at && (
                  <span className="size-2 rounded-full bg-primary" aria-label="Unread" />
                )}
                {n.link ? (
                  <Link
                    to={n.link}
                    onClick={() => !n.read_at && markRead.mutate(n.id)}
                    className="font-medium hover:text-primary hover:underline"
                  >
                    {n.title}
                  </Link>
                ) : (
                  <span className="font-medium">{n.title}</span>
                )}
                {n.severity !== 'info' && (
                  <Badge variant={SEVERITY[n.severity] ?? 'outline'}>{n.severity}</Badge>
                )}
              </p>
              {n.body && <p className="mt-0.5 text-muted-foreground">{n.body}</p>}
              <p className="mt-0.5 text-xs text-muted-foreground">{formatRelative(n.created_at)}</p>
            </div>
            {!n.read_at && (
              <Button size="sm" variant="ghost" onClick={() => markRead.mutate(n.id)}>
                Mark read
              </Button>
            )}
          </li>
        ))}
      </ul>
      {pages > 1 && (
        <div className="mt-4 flex items-center gap-2 text-sm">
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="text-muted-foreground">
            Page {page} of {pages}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </>
  )
}
