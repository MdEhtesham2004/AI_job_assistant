import { ArrowRight, Briefcase, Inbox, Mail, Send, Sparkles, Timer } from 'lucide-react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { STATUS_LABELS } from '@/features/applications/api'
import {
  RESUME_LABELS,
  SOURCE_LABELS,
  STAGES,
  useDashboard,
  useUsage,
} from '@/features/dashboard/api'
import { DigestCard } from '@/features/hunt/components/DigestCard'
import { formatDate, formatRelative } from '@/lib/format'

const pct = (value) => (value == null ? '—' : `${Math.round(value * 100)}%`)

/** Phase 14: the home page is the dashboard. */
export default function HomePage() {
  const { user } = useAuth()
  const firstName = user?.full_name?.split(' ')[0]
  const dashboard = useDashboard()
  const data = dashboard.data

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome, ${firstName}` : 'Welcome'}
        description="Your job search at a glance."
      />
      {dashboard.isPending && <p className="text-muted-foreground">Loading…</p>}
      {dashboard.isError && <p className="text-destructive">{dashboard.error.message}</p>}
      {data && <Dashboard data={data} />}
    </>
  )
}

function Tile({ label, value, hint, to }) {
  const body = (
    <CardContent className="py-4">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </CardContent>
  )
  return (
    <Card className={to ? 'transition-colors hover:border-primary/50' : undefined}>
      {to ? (
        <Link to={to} className="block" aria-label={`${label}: ${value}`}>
          {body}
        </Link>
      ) : (
        body
      )}
    </Card>
  )
}

function Dashboard({ data }) {
  return (
    <div className="flex flex-col gap-6">
      {data.waiting_for_approval > 0 && (
        <Link
          to="/outbox"
          className="flex items-center justify-between gap-3 rounded-lg border border-primary/40 bg-primary/5 px-4 py-3 text-sm hover:bg-primary/10"
        >
          <span className="flex items-center gap-2">
            <Inbox className="size-4 text-primary" aria-hidden="true" />
            <span>
              <span className="font-medium">{data.waiting_for_approval}</span> application
              {data.waiting_for_approval === 1 ? '' : 's'} waiting for your approval
            </span>
          </span>
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      )}

      <section
        aria-label="Key numbers"
        className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7"
      >
        <Tile
          label="Jobs found"
          value={data.jobs_found}
          hint={`${data.jobs_new_this_week} this week`}
          to="/jobs"
        />
        <Tile label="Waiting for approval" value={data.waiting_for_approval} to="/outbox" />
        <Tile label="Applied" value={data.applied_total} to="/applications" />
        <Tile
          label="Responses"
          value={data.responses}
          hint={`${pct(data.response_rate)} response rate`}
        />
        <Tile label="Interviews" value={data.interviews} />
        <Tile label="Offers" value={data.offers} />
        <Tile label="Rejected" value={data.rejected} />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-6">
          <Pipeline stages={data.stages} />
          <Card>
            <CardHeader>
              <CardTitle>Response rate</CardTitle>
              <CardDescription>
                Of applications that went out, how many got an answer (responded, interview, offer
                or rejection).
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-6 sm:grid-cols-2">
              <RateTable
                title="By job source"
                column="Source"
                rows={data.by_source}
                labels={SOURCE_LABELS}
              />
              <RateTable
                title="By resume"
                column="Resume"
                rows={data.by_resume}
                labels={RESUME_LABELS}
              />
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="grid grid-cols-3 gap-3 py-4 text-sm">
              <Mini
                icon={Send}
                label="Emails sent"
                value={data.emails_sent}
                hint={`${data.emails_sent_today} today`}
              />
              <Mini icon={Timer} label="Tasks running" value={data.tasks_running} />
              <Mini
                icon={Sparkles}
                label="AI this month"
                value={`$${Number(data.ai_cost_month_usd).toFixed(2)}`}
              />
            </CardContent>
          </Card>
          <DigestCard />
          <UsageCard />
          <Activity items={data.activity} />
        </div>
      </div>
    </div>
  )
}

/** This month vs. the limits the admin set (0 = unlimited). */
function UsageCard() {
  const usage = useUsage()
  const u = usage.data
  if (!u) return null
  const rows = [
    ['Job searches', u.jsearch_month, 'requests this month'],
    ['LinkedIn posts', u.apify_month, 'this month'],
    ['LinkedIn fetches', u.apify_today, 'today'],
    ...(u.interviews_month ? [['Mock interviews', u.interviews_month, 'this month']] : []),
  ]
  const budget = Number(u.ai_budget_usd)
  const spent = Number(u.ai_spent_month_usd)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your usage</CardTitle>
        <CardDescription>
          Resets on {formatDate(u.resets_at)}. Searches someone ran recently are reused for free
          {u.cached_hits_month > 0 && ` (${u.cached_hits_month} this month)`}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {rows.map(([label, q, period]) => (
          <Meter
            key={`${label}-${period}`}
            label={`${label} ${period}`}
            used={q.used}
            limit={q.limit}
            text={q.limit ? `${q.used} / ${q.limit}` : `${q.used} · no limit`}
          />
        ))}
        <Meter
          label="AI this month"
          used={spent}
          limit={budget}
          text={`$${spent.toFixed(2)} / $${budget.toFixed(2)}`}
        />
      </CardContent>
    </Card>
  )
}

function Meter({ label, used, limit, text }) {
  const share = limit ? Math.min(1, used / limit) : 0
  return (
    <div>
      <p className="flex justify-between gap-2">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">{text}</span>
      </p>
      {limit > 0 && (
        <div
          className="mt-1 h-1.5 rounded-full bg-muted"
          role="meter"
          aria-label={label}
          aria-valuenow={used}
          aria-valuemin={0}
          aria-valuemax={limit}
        >
          <div
            className={
              share >= 0.9 ? 'h-full rounded-full bg-destructive' : 'h-full rounded-full bg-primary'
            }
            style={{ width: `${share * 100}%` }}
          />
        </div>
      )}
    </div>
  )
}

function Mini({ icon: Icon, label, value, hint }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="size-3.5" aria-hidden="true" />
        {label}
      </p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

/** One series (applications per stage): single colour, value label on every bar. */
function Pipeline({ stages }) {
  const max = Math.max(1, ...STAGES.map((s) => stages[s.key] ?? 0))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Pipeline</CardTitle>
        <CardDescription>Applications per stage — the same columns as the board.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2" aria-label="Applications per stage">
          {STAGES.map((stage) => {
            const value = stages[stage.key] ?? 0
            return (
              <li key={stage.key}>
                <Link
                  to="/applications"
                  className="grid grid-cols-[6rem_1fr_2.5rem] items-center gap-3 rounded-md px-1 py-1 text-sm hover:bg-accent"
                  title={`${stage.label}: ${value}`}
                >
                  <span className="text-muted-foreground">{stage.label}</span>
                  <span className="h-3 rounded-r-full bg-muted/60">
                    {value > 0 && (
                      <span
                        className="block h-3 rounded-r-full bg-primary"
                        style={{ width: `${(value / max) * 100}%`, minWidth: '0.5rem' }}
                      />
                    )}
                  </span>
                  <span className="text-right font-medium tabular-nums">{value}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}

function RateTable({ title, column, rows, labels }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing applied yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-1 font-medium">{column}</th>
              <th className="py-1 text-right font-medium">Applied</th>
              <th className="py-1 text-right font-medium">Answered</th>
              <th className="py-1 text-right font-medium">Rate</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-t">
                <td className="py-1">{labels[row.key] ?? row.key}</td>
                <td className="py-1 text-right tabular-nums">{row.applied}</td>
                <td className="py-1 text-right tabular-nums">{row.responded}</td>
                <td className="py-1 text-right font-medium tabular-nums">{pct(row.rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function Activity({ items }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent activity</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>No applications yet.</p>
            <Link
              to="/jobs/search"
              className="inline-flex items-center gap-1.5 text-primary hover:underline"
            >
              <Briefcase className="size-4" aria-hidden="true" />
              Find jobs
            </Link>
          </div>
        ) : (
          <ul className="space-y-3 text-sm">
            {items.map((item, index) => (
              <li key={`${item.application_id}-${index}`} className="flex gap-2">
                <Mail className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <div className="min-w-0">
                  <Link
                    to={`/applications/${item.application_id}`}
                    className="font-medium hover:text-primary hover:underline"
                  >
                    {item.job_title}
                  </Link>
                  <span className="text-muted-foreground"> · {item.company}</span>
                  <p className="text-xs text-muted-foreground">
                    {STATUS_LABELS[item.to_status]}
                    {item.source === 'email_reply' ? ' · from a reply' : ''} ·{' '}
                    {formatRelative(item.at)}
                  </p>
                  {item.note && <p className="truncate text-xs">{item.note}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
