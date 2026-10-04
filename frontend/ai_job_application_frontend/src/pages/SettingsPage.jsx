import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'
import { useAuth } from '@/auth/useAuth'
import { CheckboxField } from '@/components/common/CheckboxField'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useSettings, useUpdateSettings } from '@/features/account/hooks'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { WEIGHT_FIELDS, keywordList, settingsSchema } from '@/features/account/schemas'
import { GmailCard } from '@/features/outreach/components/GmailCard'
import { usePlatformSettings, useUpdatePlatform } from '@/features/outreach/hooks'
import { applyServerErrors } from '@/lib/forms'
import { cn } from '@/lib/utils'

const num = { valueAsNumber: true }

function Section({ title, description, usedFrom, children }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          {description}
          {usedFrom && <span className="ml-1 italic">(used from {usedFrom})</span>}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">{children}</CardContent>
    </Card>
  )
}

/** API settings → form values (money as a number, keywords as one comma-separated line). */
function toForm(settings) {
  return {
    ...settings,
    monthly_ai_budget_usd: Number(settings.monthly_ai_budget_usd),
    automation_keywords: (settings.automation_keywords ?? []).join(', '),
  }
}

function SettingsForm({ settings }) {
  const update = useUpdateSettings()
  const defaults = toForm(settings)
  const {
    register,
    handleSubmit,
    setError,
    reset,
    control,
    formState: { errors, isSubmitting, isDirty, dirtyFields },
  } = useForm({ resolver: zodResolver(settingsSchema), defaultValues: defaults })

  const weights = useWatch({ control, name: 'score_weights' })
  const weightSum = Object.values(weights ?? {}).reduce((sum, n) => sum + (Number(n) || 0), 0)

  const onSubmit = async (values) => {
    // Send only what changed (PATCH semantics); weights always as a complete set.
    const changes = Object.fromEntries(Object.keys(dirtyFields).map((key) => [key, values[key]]))
    if ('automation_keywords' in changes) {
      changes.automation_keywords = keywordList(changes.automation_keywords)
    }
    try {
      const saved = await update.mutateAsync(changes)
      reset(toForm(saved))
      toast.success('Settings saved.')
    } catch (error) {
      if (error?.code === 'INVALID_THRESHOLDS') {
        setError('threshold_tailor', { type: 'server', message: error.message })
        return
      }
      applyServerErrors(error, setError, Object.keys(defaults))
    }
  }

  return (
    <form className="flex max-w-3xl flex-col gap-6" onSubmit={handleSubmit(onSubmit)} noValidate>
      <FormError message={errors.root?.server?.message} />

      <Section
        title="Job matching"
        description="How jobs are scored against your resume."
        usedFrom="Phase 9"
      >
        <FormField
          label="Use master resume at score ≥"
          type="number"
          registration={register('threshold_use_master', num)}
          error={errors.threshold_use_master}
        />
        <FormField
          label="Tailor resume at score ≥"
          type="number"
          hint="Below this the job is skipped."
          registration={register('threshold_tailor', num)}
          error={errors.threshold_tailor}
        />
        <div className="sm:col-span-2">
          <p className="mb-2 text-sm font-medium">
            Score weights{' '}
            <span
              className={cn('text-xs', weightSum === 100 ? 'text-success' : 'text-destructive')}
            >
              (total {weightSum} / 100)
            </span>
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {WEIGHT_FIELDS.map(([key, label]) => (
              <FormField
                key={key}
                label={label}
                type="number"
                registration={register(`score_weights.${key}`, num)}
                error={errors.score_weights?.[key]}
              />
            ))}
          </div>
          {errors.score_weights?.root && (
            <p className="mt-1 text-xs text-destructive">{errors.score_weights.root.message}</p>
          )}
          {errors.score_weights?.message && (
            <p className="mt-1 text-xs text-destructive">{errors.score_weights.message}</p>
          )}
        </div>
        {/* Match scores are made only on demand (admin decision, Phase 9) — no auto-analysis. */}
      </Section>

      <Section
        title="Email sending"
        description="Safety limits for applications sent from your Gmail."
        usedFrom="Phase 12"
      >
        <FormField
          label="Daily send limit"
          type="number"
          registration={register('daily_send_cap', num)}
          error={errors.daily_send_cap}
        />
        <FormField
          label="Seconds between emails"
          type="number"
          registration={register('send_interval_seconds', num)}
          error={errors.send_interval_seconds}
        />
        <FormField
          label="Days before emailing the same person again"
          type="number"
          registration={register('recipient_cooldown_days', num)}
          error={errors.recipient_cooldown_days}
        />
        <FormField
          label="Follow-up after (days, 0 = off)"
          type="number"
          registration={register('follow_up_days', num)}
          error={errors.follow_up_days}
        />
        <FormField
          label="Mark 'no response' after (days)"
          type="number"
          registration={register('no_response_days', num)}
          error={errors.no_response_days}
        />
        <div className="sm:col-span-2">
          <CheckboxField
            label="LinkedIn hiring posts"
            description="Find recruiter emails in public LinkedIn hiring posts (via Apify) on the Contacts page. Every contact still needs your approval."
            registration={register('linkedin_source_enabled')}
          />
        </div>
      </Section>

      <Section
        title="Automation"
        description="Runs only when you click it in the Outbox: scores your jobs, prepares the documents and drafts the emails. Nothing is sent until you approve it."
      >
        <div className="sm:col-span-2">
          <FormField
            label="Keywords for fetching new jobs (comma-separated, up to 5)"
            hint="Used only by 'Fetch new jobs & automate' — each keyword is one LinkedIn search. Shorter finds more, e.g. Data Scientist."
            registration={register('automation_keywords')}
            error={errors.automation_keywords}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="automation-posted">Fetch posts from the last</Label>
          <Select id="automation-posted" {...register('automation_posted_limit')}>
            <option value="24h">24 hours</option>
            <option value="week">week</option>
            <option value="month">month</option>
          </Select>
        </div>
        <FormField
          label="Minimum match score"
          type="number"
          hint="Jobs below this are not prepared."
          registration={register('automation_min_score', num)}
          error={errors.automation_min_score}
        />
        <FormField
          label="Applications prepared per run (max)"
          type="number"
          hint="Caps AI cost per run."
          registration={register('automation_max_jobs', num)}
          error={errors.automation_max_jobs}
        />
        <div className="sm:col-span-2 flex flex-col gap-3">
          <CheckboxField
            label="Tailor the resume when the match analysis recommends it"
            registration={register('automation_tailor')}
          />
          <CheckboxField
            label="Write a cover letter and attach it"
            registration={register('automation_cover_letter')}
          />
        </div>
      </Section>

      <Section
        title="AI usage"
        description="Monthly spending limit for AI calls."
        usedFrom="Phase 6"
      >
        <FormField
          label="Monthly AI budget (USD)"
          type="number"
          step="0.01"
          registration={register('monthly_ai_budget_usd', num)}
          error={errors.monthly_ai_budget_usd}
        />
      </Section>

      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting || !isDirty}>
          {isSubmitting ? 'Saving…' : 'Save settings'}
        </Button>
        <Button type="button" variant="outline" disabled={!isDirty} onClick={() => reset(defaults)}>
          Discard changes
        </Button>
      </div>
    </form>
  )
}

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
  const update = useUpdatePlatform()
  const enabled = platform.data?.automation_fetch_enabled ?? false
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
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-primary"
            checked={enabled}
            disabled={platform.isPending || update.isPending}
            onChange={(e) => update.mutate({ automation_fetch_enabled: e.target.checked })}
          />
          <span>
            <span className="font-medium">Allow “Fetch new jobs &amp; automate”</span>
            <span className="block text-muted-foreground">
              Lets users search LinkedIn hiring posts from the Outbox automation. Each run uses
              Apify credit (about 25 posts per keyword) plus AI for every new post.
            </span>
          </span>
        </label>
        {platform.data && <QuotaForm key={JSON.stringify(platform.data)} saved={platform.data} />}
      </CardContent>
    </Card>
  )
}

const QUOTAS = [
  ['jsearch_requests_per_month', 'Job-search requests per user / month', 'One per results page.'],
  ['apify_posts_per_month', 'LinkedIn posts per user / month', 'Apify bills per post read.'],
  ['apify_runs_per_day', 'LinkedIn fetches per user / day', ''],
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
