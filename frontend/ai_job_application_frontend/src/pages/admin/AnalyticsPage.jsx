import { Bug } from 'lucide-react'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAnalytics, useRecentErrors, useTestError } from '@/features/admin/insights'
import { formatDateTime, formatRelative } from '@/lib/format'

const usd = (value) => `$${Number(value).toFixed(2)}`

const PROVIDERS = {
  jsearch: { label: 'JSearch (job search)', unit: 'requests' },
  apify: { label: 'Apify (LinkedIn posts)', unit: 'posts' },
}

/** Paid data APIs this month: real calls vs. answers from the shared cache. */
function ProviderCard({ data }) {
  const rows = data.providers ?? []
  const left = data.jsearch_quota_remaining
  return (
    <Card>
      <CardHeader>
        <CardTitle>Search APIs (this month)</CardTitle>
        <CardDescription>
          Identical searches by any user reuse stored results (JSearch 12 h, LinkedIn 24 h) — those
          are free and count against no quota.
          {left != null && ` JSearch plan: ${left} requests left.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-1 font-medium">Provider</th>
              <th className="py-1 text-right font-medium">Paid calls</th>
              <th className="py-1 text-right font-medium">From cache</th>
              <th className="py-1 text-right font-medium">Billed units</th>
              <th className="py-1 text-right font-medium">Est. cost</th>
              <th className="py-1 text-right font-medium">Failed</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.provider} className="border-t">
                <td className="py-1">{PROVIDERS[p.provider]?.label ?? p.provider}</td>
                <td className="py-1 text-right tabular-nums">{p.calls}</td>
                <td className="py-1 text-right tabular-nums">
                  {p.cache_hits}
                  {p.cache_rate != null && (
                    <span className="text-xs text-muted-foreground">
                      {' '}
                      ({Math.round(p.cache_rate * 100)}%)
                    </span>
                  )}
                </td>
                <td className="py-1 text-right tabular-nums">
                  {p.units} {PROVIDERS[p.provider]?.unit}
                </td>
                <td className="py-1 text-right tabular-nums">
                  {Number(p.cost_usd) > 0 ? usd(p.cost_usd) : '—'}
                </td>
                <td className="py-1 text-right tabular-nums">{p.failed}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="text-sm text-muted-foreground">No job or LinkedIn searches this month.</p>
        )}
      </CardContent>
    </Card>
  )
}

export default function AnalyticsPage() {
  const analytics = useAnalytics()
  const errors = useRecentErrors()
  const testError = useTestError()
  const data = analytics.data

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Platform usage and cost — all users."
        actions={
          <Button
            variant="outline"
            onClick={() => testError.mutate()}
            disabled={testError.isPending}
          >
            <Bug />
            Send test error
          </Button>
        }
      />
      {analytics.isPending && <p className="text-muted-foreground">Loading…</p>}
      {data && (
        <div className="flex flex-col gap-6">
          <section
            aria-label="Totals"
            className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
          >
            {[
              ['Approved users', data.users_by_status.approved ?? 0],
              ['Waiting for approval', data.users_by_status.pending ?? 0],
              ['Jobs in catalog', data.jobs_in_catalog],
              ['Applications', data.applications_total],
              ['Emails sent (30 days)', data.emails_sent_30d],
              ['AI this month', `${usd(data.ai_cost_month_usd)} · ${data.ai_calls_month} calls`],
            ].map(([label, value]) => (
              <Card key={label}>
                <CardContent className="py-4">
                  <p className="text-xs font-medium text-muted-foreground">{label}</p>
                  <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
                </CardContent>
              </Card>
            ))}
          </section>

          <ProviderCard data={data} />

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>AI cost by feature (this month)</CardTitle>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="py-1 font-medium">Feature</th>
                      <th className="py-1 text-right font-medium">Calls</th>
                      <th className="py-1 text-right font-medium">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.ai_cost_by_feature.map((row) => (
                      <tr key={row.feature} className="border-t">
                        <td className="py-1 font-mono text-xs">{row.feature}</td>
                        <td className="py-1 text-right tabular-nums">{row.calls}</td>
                        <td className="py-1 text-right tabular-nums">{usd(row.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {data.ai_cost_by_feature.length === 0 && (
                  <p className="text-sm text-muted-foreground">No AI calls this month.</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Users</CardTitle>
                <CardDescription>Highest AI cost first.</CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="py-1 font-medium">User</th>
                      <th className="py-1 text-right font-medium">Applications</th>
                      <th className="py-1 text-right font-medium">Emails (30d)</th>
                      <th className="py-1 text-right font-medium">AI (month)</th>
                      <th className="py-1 text-right font-medium">Job searches</th>
                      <th className="py-1 text-right font-medium">LinkedIn posts</th>
                      <th className="py-1 text-right font-medium">Last sign-in</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.users.map((u) => (
                      <tr key={u.user_id} className="border-t">
                        <td className="py-1">
                          {u.full_name}
                          <div className="text-xs text-muted-foreground">{u.email}</div>
                        </td>
                        <td className="py-1 text-right tabular-nums">{u.applications}</td>
                        <td className="py-1 text-right tabular-nums">{u.emails_sent_30d}</td>
                        <td className="py-1 text-right tabular-nums">{usd(u.ai_cost_month_usd)}</td>
                        <td className="py-1 text-right tabular-nums">
                          {u.jsearch_requests_month ?? 0}
                        </td>
                        <td className="py-1 text-right tabular-nums">{u.apify_posts_month ?? 0}</td>
                        <td className="py-1 text-right text-xs text-muted-foreground">
                          {u.last_login_at ? formatRelative(u.last_login_at) : 'never'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Recent errors</CardTitle>
              <CardDescription>
                Background tasks that failed ({data.failed_tasks_7d} in the last 7 days). Unexpected
                API errors go to Sentry when SENTRY_DSN is set.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              {errors.data?.length === 0 && (
                <p className="text-sm text-muted-foreground">No failed tasks.</p>
              )}
              <ul className="divide-y text-sm">
                {errors.data?.map((e) => (
                  <li key={e.task_id} className="py-2">
                    <p className="flex flex-wrap gap-x-2">
                      <span className="font-mono text-xs">{e.type}</span>
                      <span className="text-xs text-muted-foreground">
                        {e.user_email ?? 'system'} · {formatDateTime(e.created_at)} · attempt{' '}
                        {e.attempts}
                      </span>
                    </p>
                    <p className="text-destructive">{e.error}</p>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}
    </>
  )
}
