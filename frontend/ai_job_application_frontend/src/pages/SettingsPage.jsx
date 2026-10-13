import { useQueryClient } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'
import { useAuth } from '@/auth/useAuth'
import { FormError } from '@/components/common/FormError'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useSettings } from '@/features/account/hooks'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { SettingsForm } from '@/features/account/components/SettingsForm'
import { GmailCard } from '@/features/outreach/components/GmailCard'
import { usePlatformSettings, useUpdatePlatform } from '@/features/outreach/hooks'

/** Google sends the browser back here with ?gmail=connected|error — say so once. */
function useGmailRedirectNotice() {
  const [params, setParams] = useSearchParams()
  const queryClient = useQueryClient()
  const result = params.get('gmail')
  useEffect(() => {
    if (!result) return
    if (result === 'connected') toast.success(`Gmail connected: ${params.get('account') ?? ''}`)
    else toast.error(params.get('message') ?? 'Gmail was not connected.')
    queryClient.invalidateQueries({ queryKey: queryKeys.gmail.status() })
    setParams({}, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per redirect
  }, [result])
}

/** Admin only: platform-wide switches (all users). */
function PlatformCard() {
  const platform = usePlatformSettings({ enabled: true })
  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
          Platform (admin)
        </CardTitle>
        <CardDescription>Applies to every user of this platform.</CardDescription>
      </CardHeader>
      <CardContent>
        {platform.data && <QuotaForm key={JSON.stringify(platform.data)} saved={platform.data} />}
      </CardContent>
    </Card>
  )
}

const QUOTAS = [
  ['jsearch_requests_per_month', 'Job-search requests per user / month', 'One per results page.'],
  ['apify_posts_per_month', 'LinkedIn posts per user / month', 'Apify bills per post read.'],
  ['apify_runs_per_day', 'LinkedIn fetches per user / day', ''],
  [
    'interviews_per_month',
    'Mock interviews per user / month',
    'Voice calls (about $0.30–1 each); practising again counts.',
  ],
]

const POSTS_PER_FETCH = [10, 25, 50]

/** Paid-API limits per user. Searches someone already ran (cached) never count. */
function QuotaForm({ saved }) {
  const update = useUpdatePlatform()
  const [values, setValues] = useState(() =>
    Object.fromEntries(QUOTAS.map(([name]) => [name, String(saved[name] ?? 0)])),
  )
  const [maxPages, setMaxPages] = useState(saved.jsearch_max_pages ?? 1)
  const [loadMore, setLoadMore] = useState(saved.jsearch_allow_load_more ?? true)
  const [maxPosts, setMaxPosts] = useState(saved.apify_max_posts_per_fetch ?? 25)
  const changes = Object.fromEntries(
    [
      ...QUOTAS.map(([name]) => [name, Number(values[name])]),
      ['jsearch_max_pages', maxPages],
      ['jsearch_allow_load_more', loadMore],
      ['apify_max_posts_per_fetch', maxPosts],
    ].filter(([name, value]) => value !== saved[name]),
  )
  // Keep a value set elsewhere (e.g. via the API) selectable.
  const postChoices = [...new Set([...POSTS_PER_FETCH, maxPosts])].sort((a, b) => a - b)
  const invalid = QUOTAS.some(
    ([name]) => values[name] === '' || !Number.isInteger(Number(values[name])) || values[name] < 0,
  )
  return (
    <form
      className="mt-6 flex flex-col gap-3 border-t pt-4"
      onSubmit={(e) => {
        e.preventDefault()
        update.mutate(changes)
      }}
    >
      <div>
        <p className="text-sm font-medium">Usage limits</p>
        <p className="text-sm text-muted-foreground">
          Paid search calls each user may make. 0 = unlimited. A search any user ran recently is
          reused for free and does not count.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {QUOTAS.map(([name, label, hint]) => (
          <div key={name} className="flex flex-col gap-1">
            <Label htmlFor={name}>{label}</Label>
            <Input
              id={name}
              type="number"
              min={0}
              step={1}
              value={values[name]}
              onChange={(e) => setValues((v) => ({ ...v, [name]: e.target.value }))}
            />
            {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
          </div>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="jsearch_max_pages">Most jobs per search</Label>
          <Select
            id="jsearch_max_pages"
            value={maxPages}
            onChange={(e) => setMaxPages(Number(e.target.value))}
          >
            <option value={1}>10 jobs (1 request)</option>
            <option value={2}>20 jobs (2 requests)</option>
            <option value={3}>30 jobs (3 requests)</option>
          </Select>
          <p className="text-xs text-muted-foreground">
            JSearch bills per page of 10, so smaller steps would not save anything.
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="apify_max_posts_per_fetch">Most posts per LinkedIn fetch</Label>
          <Select
            id="apify_max_posts_per_fetch"
            value={maxPosts}
            onChange={(e) => setMaxPosts(Number(e.target.value))}
          >
            {postChoices.map((n) => (
              <option key={n} value={n}>
                {n} posts
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">Also used per keyword by automation.</p>
        </div>
        <label className="flex items-start gap-3 text-sm sm:pt-6">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-primary"
            checked={loadMore}
            onChange={(e) => setLoadMore(e.target.checked)}
          />
          <span>
            <span className="font-medium">Allow “Load more” on search results</span>
            <span className="block text-muted-foreground">
              Each click fetches the next 10 jobs (one more request, counted in the monthly limit).
            </span>
          </span>
        </label>
      </div>
      <div>
        <Button
          type="submit"
          size="sm"
          disabled={invalid || Object.keys(changes).length === 0 || update.isPending}
        >
          Save limits
        </Button>
      </div>
    </form>
  )
}

export default function SettingsPage() {
  const settings = useSettings()
  const { user } = useAuth()
  useGmailRedirectNotice()
  return (
    <>
      <PageHeader title="Settings" description="Your preferences. Saved per account." />
      <div className="mb-6 flex flex-col gap-6">
        <GmailCard />
        {user?.role === 'admin' && <PlatformCard />}
      </div>
      {settings.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
      {settings.isError && <FormError message={settings.error.message} />}
      {settings.data && <SettingsForm settings={settings.data} />}
    </>
  )
}
