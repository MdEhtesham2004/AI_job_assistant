import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm, useWatch } from 'react-hook-form'

import { CheckboxField } from '@/components/common/CheckboxField'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useSettings } from '@/features/account/hooks'
import { useUsage } from '@/features/dashboard/api'
import { applyServerErrors } from '@/lib/forms'

import { EXPERIENCE_OPTIONS, SCHEDULE_PRESETS } from '../api'
import { useCreateSavedSearch, useUpdateSavedSearch } from '../hooks'
import { savedSearchSchema, toSearchBody } from '../schemas'

const CUSTOM = 'custom'

// Phase 19: recruiter emails from LinkedIn hiring posts (only for admin-allowed users).
const LINKEDIN = 'linkedin'
const LINKEDIN_CRON = '0 9 * * *'

function initialValues(saved, prefill) {
  const source = saved ?? prefill ?? {}
  const cron = saved?.schedule_cron ?? SCHEDULE_PRESETS[0].cron
  const preset = SCHEDULE_PRESETS.some((p) => p.cron === cron)
  return {
    name:
      source.name ??
      (source.keywords
        ? `${source.keywords}${source.location ? ` · ${source.location}` : ''}`
        : ''),
    keywords: source.keywords ?? '',
    location: source.location ?? '',
    experience: source.experience ?? '',
    remote_only: source.remote_only ?? false,
    country: source.country ?? 'in',
    schedule: preset ? cron : CUSTOM,
    custom_cron: preset ? '' : cron,
    kind: saved?.kind ?? 'jobs',
    posted_limit: saved?.posted_limit ?? '24h',
    max_posts: saved?.max_posts ?? 25,
  }
}

/** Create or edit a saved search. `prefill` copies the current search form. */
export function SavedSearchDialog({ open, onClose, saved, prefill }) {
  const create = useCreateSavedSearch()
  const update = useUpdateSavedSearch()
  const linkedinAllowed = useSettings().data?.linkedin_schedule_allowed ?? false
  // Apify bills per post: 5, 10, 15 … up to the admin's cap (Settings › Platform).
  const cap = useUsage().data?.max_posts_per_fetch ?? 25
  const postOptions = Array.from({ length: Math.floor(cap / 5) }, (_, i) => (i + 1) * 5)
  const {
    register,
    handleSubmit,
    control,
    setError,
    setValue,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(savedSearchSchema),
    // The dialog is mounted fresh each time it opens, so defaults are enough.
    defaultValues: initialValues(saved, prefill),
  })
  const largest = postOptions.at(-1) ?? 5
  useEffect(() => {
    if (Number(getValues('max_posts')) > largest) setValue('max_posts', largest)
  }, [largest, getValues, setValue])
  const schedule = useWatch({ control, name: 'schedule' })
  const kind = useWatch({ control, name: 'kind' })
  const isLinkedin = kind === LINKEDIN

  const onSubmit = async (values) => {
    const body = {
      ...toSearchBody(values),
      name: values.name,
      schedule_cron: values.schedule === CUSTOM ? values.custom_cron : values.schedule,
      ...(values.kind === LINKEDIN && {
        posted_limit: values.posted_limit,
        max_posts: Number(values.max_posts),
      }),
      ...(!saved && { kind: values.kind }), // the type is fixed once created
    }
    try {
      if (saved) await update.mutateAsync({ id: saved.id, changes: body })
      else await create.mutateAsync(body)
      onClose()
    } catch (error) {
      applyServerErrors(error, setError, ['name', 'keywords', 'location', 'country', 'max_posts'])
    }
  }
  const kindField = register('kind')

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={saved ? 'Edit saved search' : 'New saved search'}
      description={
        isLinkedin
          ? "Runs on its schedule (your profile's time zone) and adds recruiter contacts from LinkedIn hiring posts for you to approve. Nothing is emailed automatically."
          : "Runs automatically on its schedule (your profile's time zone) and notifies you about new jobs."
      }
      className="max-w-lg"
    >
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
        <FormError message={errors.root?.server?.message} />
        {(linkedinAllowed || saved?.kind === LINKEDIN) && (
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="saved-kind">What to fetch</Label>
            <Select
              id="saved-kind"
              disabled={Boolean(saved)}
              {...kindField}
              onChange={(event) => {
                kindField.onChange(event)
                if (event.target.value === LINKEDIN) setValue('schedule', LINKEDIN_CRON)
              }}
            >
              <option value="jobs">Jobs</option>
              <option value={LINKEDIN}>Recruiter emails (LinkedIn hiring posts)</option>
            </Select>
          </div>
        )}
        <div className="sm:col-span-2">
          <FormField label="Name" registration={register('name')} error={errors.name} />
        </div>
        <FormField label="Keywords" registration={register('keywords')} error={errors.keywords} />
        {isLinkedin ? (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="saved-posted">Posts from</Label>
              <Select id="saved-posted" {...register('posted_limit')}>
                <option value="24h">Last 24 hours</option>
                <option value="week">Last week</option>
                <option value="month">Last month</option>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="saved-max-posts">Posts per fetch</Label>
              <Select id="saved-max-posts" {...register('max_posts')}>
                {postOptions.map((count) => (
                  <option key={count} value={count}>
                    {count} posts
                  </option>
                ))}
              </Select>
              {errors.max_posts && (
                <p className="text-xs text-destructive">{errors.max_posts.message}</p>
              )}
            </div>
          </>
        ) : (
          <>
            <FormField
              label="Location"
              placeholder="e.g. Hyderabad"
              registration={register('location')}
              error={errors.location}
            />
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="saved-experience">Experience</Label>
              <Select id="saved-experience" {...register('experience')}>
                {EXPERIENCE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </div>
            <FormField label="Country" registration={register('country')} error={errors.country} />
          </>
        )}
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="saved-schedule">Schedule</Label>
          <Select id="saved-schedule" {...register('schedule')}>
            {SCHEDULE_PRESETS.map((preset) => (
              <option key={preset.cron} value={preset.cron}>
                {preset.label}
              </option>
            ))}
            <option value={CUSTOM}>Custom (cron)</option>
          </Select>
        </div>
        {schedule === CUSTOM && (
          <div className="sm:col-span-2">
            <FormField
              label="Cron schedule"
              placeholder="minute hour day month weekday, e.g. 30 7 * * 1-5"
              hint="At most once per hour."
              registration={register('custom_cron')}
              error={errors.custom_cron}
            />
          </div>
        )}
        {!isLinkedin && (
          <div className="sm:col-span-2">
            <CheckboxField label="Remote jobs only" registration={register('remote_only')} />
          </div>
        )}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : saved ? 'Save changes' : 'Create'}
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
