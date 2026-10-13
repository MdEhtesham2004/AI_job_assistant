import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'

import { CheckboxField } from '@/components/common/CheckboxField'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { applyServerErrors } from '@/lib/forms'
import { cn } from '@/lib/utils'

import { useUpdateSettings } from '../hooks'
import { WEIGHT_FIELDS, settingsSchema } from '../schemas'

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

/** API settings → form values (money as a number). */
function toForm(settings) {
  return { ...settings, monthly_ai_budget_usd: Number(settings.monthly_ai_budget_usd) }
}

/** All your settings in one form; only changed fields are sent (PATCH). */
export function SettingsForm({ settings }) {
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
        title="Automations › Daily digest"
        description="Every morning: your best new matches, scored for you (up to 20 new jobs a day), in the app and — when Gmail is connected — by email to yourself."
      >
        <div className="sm:col-span-2">
          <CheckboxField label="Send me a daily digest" registration={register('digest_enabled')} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="digest-hour">Time (your time zone, from Profile)</Label>
          <Select id="digest-hour" {...register('digest_hour', num)}>
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, '0')}:00
              </option>
            ))}
          </Select>
        </div>
        <FormField
          label="Only jobs scoring at least"
          type="number"
          registration={register('digest_min_score', num)}
          error={errors.digest_min_score}
        />
        <div className="sm:col-span-2">
          <CheckboxField
            label="Also email it to me (from my connected Gmail, to myself)"
            registration={register('digest_email')}
          />
        </div>
      </Section>

      <Section
        title="Job sources"
        description="Where your jobs and contacts come from, besides job search."
      >
        <div className="sm:col-span-2">
          <CheckboxField
            label="LinkedIn hiring posts"
            description="Find recruiter emails in public LinkedIn hiring posts (via Apify) on the Contacts page. Every contact still needs your approval."
            registration={register('linkedin_source_enabled')}
          />
        </div>
      </Section>

      <Section
        title="Automations › Apply pipeline"
        description="Used when you run Automations › Apply pipeline: scores your jobs, prepares the documents and drafts the emails. Nothing is sent until you approve it in the Outbox."
      >
        <div className="sm:col-span-2">
          <CheckboxField
            label="Prepare applications by itself every day"
            description="For jobs with an approved contact; skipped when none is ready. Drafts still wait for your approval."
            registration={register('automation_enabled')}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="automation-hour">Time (your time zone, from Profile)</Label>
          <Select id="automation-hour" {...register('automation_hour', num)}>
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, '0')}:00
              </option>
            ))}
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

      <details className="group rounded-lg border bg-card">
        <summary className="cursor-pointer select-none px-6 py-4 text-sm font-medium">
          Advanced settings
          <span className="ml-2 font-normal text-muted-foreground">
            — scoring weights, sending limits, AI budget
          </span>
        </summary>
        <div className="flex flex-col gap-6 p-4 pt-0">
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
        </div>
      </details>

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
