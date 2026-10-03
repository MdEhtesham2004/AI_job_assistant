import { Columns3, Download, Rows3 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { BOARD_COLUMNS, CHANNEL_LABELS } from '@/features/applications/api'
import { ApplicationStatusBadge } from '@/features/applications/components/ApplicationStatusBadge'
import {
  useApplications,
  useApplicationCounts,
  useExportApplications,
} from '@/features/applications/hooks'
import { MatchScoreBadge } from '@/features/jobs/components/MatchScore'
import { formatDateTime, formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

const VIEW_KEY = 'applications-view'

function savedView() {
  try {
    return localStorage.getItem(VIEW_KEY) ?? 'board'
  } catch {
    return 'board'
  }
}

export default function ApplicationsPage() {
  const [view, setView] = useState(savedView)
  const [stage, setStage] = useState('')
  const [channel, setChannel] = useState('')
  const [q, setQ] = useState('')
  const statuses = BOARD_COLUMNS.find((c) => c.key === stage)?.statuses ?? []
  const filters = { statuses, channel, q, page_size: 200 }
  const applications = useApplications(filters)
  const counts = useApplicationCounts().data
  const exporter = useExportApplications()
  const items = applications.data?.items ?? []

  const switchView = (next) => {
    setView(next)
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      // the preference is a convenience only
    }
  }

  return (
    <>
      <PageHeader
        title="Applications"
        description="Every job you are applying to, from preparing to the offer."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => exporter.mutate({ statuses, channel, q })}
              disabled={exporter.isPending}
            >
              <Download />
              Export CSV
            </Button>
            <div className="flex rounded-md border" role="group" aria-label="View">
              <Button
                variant={view === 'board' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => switchView('board')}
                aria-pressed={view === 'board'}
              >
                <Columns3 />
                Board
              </Button>
              <Button
                variant={view === 'table' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => switchView('table')}
                aria-pressed={view === 'table'}
              >
                <Rows3 />
                Table
              </Button>
            </div>
          </>
        }
      />

      <div className="mb-4 grid gap-2 sm:grid-cols-[2fr_1fr_1fr]">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Job or company"
          aria-label="Job or company"
        />
        <Select aria-label="Stage" value={stage} onChange={(e) => setStage(e.target.value)}>
          <option value="">All stages</option>
          {BOARD_COLUMNS.map((column) => (
            <option key={column.key} value={column.key}>
              {column.label}
            </option>
          ))}
        </Select>
        <Select aria-label="Channel" value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">All channels</option>
          {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      {applications.isPending && <p className="text-muted-foreground">Loading…</p>}
      {applications.isSuccess && counts?.total === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No applications yet. Open a job and use{' '}
            <span className="font-medium">Prepare application</span>.{' '}
            <Link to="/jobs" className="text-primary hover:underline">
              Go to Jobs
            </Link>
          </CardContent>
        </Card>
      )}
      {applications.isSuccess &&
        counts?.total !== 0 &&
        (view === 'board' ? <Board items={items} /> : <Table items={items} />)}
    </>
  )
}

function Board({ items }) {
  return (
    <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
      {BOARD_COLUMNS.map((column) => {
        const cards = items.filter((a) => column.statuses.includes(a.status))
        return (
          <section
            key={column.key}
            aria-label={column.label}
            className="rounded-lg bg-muted/40 p-2"
          >
            <h2 className="mb-2 flex items-center justify-between px-1 text-sm font-semibold">
              {column.label}
              <span className="text-xs text-muted-foreground">{cards.length}</span>
            </h2>
            <ul className="space-y-2">
              {cards.map((a) => (
                <li key={a.id} className="rounded-md border bg-card p-3 text-sm shadow-xs">
                  <Link
                    to={`/applications/${a.id}`}
                    className="font-medium hover:text-primary hover:underline"
                  >
                    {a.job.title}
                  </Link>
                  <p className="truncate text-xs text-muted-foreground">{a.job.company}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <ApplicationStatusBadge status={a.status} />
                    <MatchScoreBadge score={a.match_score} />
                  </div>
                  {a.next_action && (
                    <p className="mt-1.5 text-xs">
                      <span className="text-muted-foreground">Next:</span> {a.next_action}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatRelative(a.last_status_at)}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

function Table({ items }) {
  return (
    <Card>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="border-b text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Job</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Channel</th>
              <th className="px-4 py-2 font-medium">Score</th>
              <th className="px-4 py-2 font-medium">Applied</th>
              <th className="px-4 py-2 font-medium">Next action</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((a) => (
              <tr key={a.id} className="align-top">
                <td className="px-4 py-2">
                  <Link to={`/applications/${a.id}`} className="font-medium hover:underline">
                    {a.job.title}
                  </Link>
                  <div className="text-xs text-muted-foreground">{a.job.company}</div>
                </td>
                <td className="px-4 py-2">
                  <ApplicationStatusBadge status={a.status} />
                </td>
                <td className="px-4 py-2">{CHANNEL_LABELS[a.channel]}</td>
                <td className={cn('px-4 py-2', a.match_score === null && 'text-muted-foreground')}>
                  {a.match_score ?? '—'}
                </td>
                <td className="px-4 py-2">{a.applied_at ? formatDateTime(a.applied_at) : '—'}</td>
                <td className="px-4 py-2">{a.next_action ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}
