import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'

import { CheckboxField } from '@/components/common/CheckboxField'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useSettings, useUpdateSettings } from '@/features/account/hooks'
import { WEIGHT_FIELDS, settingsSchema } from '@/features/account/schemas'
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

function SettingsForm({ settings }) {
  const update = useUpdateSettings()
  const defaults = { ...settings, monthly_ai_budget_usd: Number(settings.monthly_ai_budget_usd) }
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
      reset({ ...saved, monthly_ai_budget_usd: Number(saved.monthly_ai_budget_usd) })
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
      </Section>

      <Section title="Automation" description="End-to-end pipeline options." usedFrom="Phase 13">
        <div className="sm:col-span-2 flex flex-col gap-3">
          <CheckboxField
            label="Enable automation"
            description="Prepare applications automatically; you still approve every email."
            registration={register('automation_enabled')}
          />
          <CheckboxField
            label="Use LinkedIn hiring posts as a contact source"
            registration={register('linkedin_source_enabled')}
          />
        </div>
        <FormField
          label="Minimum match score for automation"
          type="number"
          registration={register('automation_min_score', num)}
          error={errors.automation_min_score}
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

export default function SettingsPage() {
  const settings = useSettings()
  return (
    <>
      <PageHeader title="Settings" description="Your preferences. Saved per account." />
      {settings.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
      {settings.isError && <FormError message={settings.error.message} />}
      {settings.data && <SettingsForm settings={settings.data} />}
    </>
  )
}
