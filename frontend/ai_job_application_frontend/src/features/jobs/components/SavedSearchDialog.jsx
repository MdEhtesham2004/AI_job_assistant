import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'

import { CheckboxField } from '@/components/common/CheckboxField'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { applyServerErrors } from '@/lib/forms'

import { EXPERIENCE_OPTIONS, SCHEDULE_PRESETS } from '../api'
import { useCreateSavedSearch, useUpdateSavedSearch } from '../hooks'
import { savedSearchSchema, toSearchBody } from '../schemas'

const CUSTOM = 'custom'

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
  }
}

/** Create or edit a saved search. `prefill` copies the current search form. */
export function SavedSearchDialog({ open, onClose, saved, prefill }) {
  const create = useCreateSavedSearch()
  const update = useUpdateSavedSearch()
  const {
    register,
    handleSubmit,
    control,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(savedSearchSchema),
    // The dialog is mounted fresh each time it opens, so defaults are enough.
    defaultValues: initialValues(saved, prefill),
  })
  const schedule = useWatch({ control, name: 'schedule' })

  const onSubmit = async (values) => {
    const body = {
      ...toSearchBody(values),
      name: values.name,
      schedule_cron: values.schedule === CUSTOM ? values.custom_cron : values.schedule,
    }
    try {
      if (saved) await update.mutateAsync({ id: saved.id, changes: body })
      else await create.mutateAsync(body)
      onClose()
    } catch (error) {
      applyServerErrors(error, setError, ['name', 'keywords', 'location', 'country'])
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={saved ? 'Edit saved search' : 'New saved search'}
      description="Runs automatically on its schedule (your profile's time zone) and notifies you about new jobs."
      className="max-w-lg"
    >
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
        <FormError message={errors.root?.server?.message} />
        <div className="sm:col-span-2">
          <FormField label="Name" registration={register('name')} error={errors.name} />
        </div>
        <FormField label="Keywords" registration={register('keywords')} error={errors.keywords} />
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
        <div className="sm:col-span-2">
          <CheckboxField label="Remote jobs only" registration={register('remote_only')} />
        </div>
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
