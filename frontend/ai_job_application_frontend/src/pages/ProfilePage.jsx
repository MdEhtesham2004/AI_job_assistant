import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import { useAuth } from '@/auth/useAuth'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { AccountDataCard } from '@/features/account/AccountDataCard'
import { accountApi } from '@/features/account/api'
import { useProfile, useUpdateProfile } from '@/features/account/hooks'
import { nameSchema, profileSchema, timeZones } from '@/features/account/schemas'
import { applyServerErrors } from '@/lib/forms'

function NameCard() {
  const { user, reloadUser } = useAuth()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting, isDirty },
    reset,
  } = useForm({ resolver: zodResolver(nameSchema), values: { full_name: user?.full_name ?? '' } })

  const onSubmit = async ({ full_name }) => {
    try {
      await accountApi.updateName(full_name)
      await reloadUser()
      reset({ full_name })
      toast.success('Name updated.')
    } catch (error) {
      applyServerErrors(error, setError, ['full_name'])
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Account</CardTitle>
        <CardDescription>Your email is used to sign in and cannot be changed here.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
          <FormField
            label="Full name"
            registration={register('full_name')}
            error={errors.full_name}
          />
          <FormField label="Email" value={user?.email ?? ''} readOnly disabled />
          <FormError message={errors.root?.server?.message} />
          <div className="sm:col-span-2">
            <Button type="submit" disabled={isSubmitting || !isDirty}>
              {isSubmitting ? 'Saving…' : 'Save name'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function ProfileForm({ profile }) {
  const zones = useMemo(() => timeZones(), [])
  const update = useUpdateProfile()
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      headline: profile.headline ?? '',
      phone: profile.phone ?? '',
      location: profile.location ?? '',
      timezone: profile.timezone,
      linkedin: profile.links.linkedin ?? '',
      github: profile.links.github ?? '',
      portfolio: profile.links.portfolio ?? '',
    },
  })

  const onSubmit = async (values) => {
    const links = Object.fromEntries(
      ['linkedin', 'github', 'portfolio']
        .filter((key) => values[key])
        .map((key) => [key, values[key]]),
    )
    try {
      await update.mutateAsync({
        headline: values.headline || null,
        phone: values.phone || null,
        location: values.location || null,
        timezone: values.timezone,
        links,
      })
      reset(values)
      toast.success('Profile saved.')
    } catch (error) {
      applyServerErrors(error, setError, ['headline', 'phone', 'location', 'timezone'])
    }
  }

  return (
    <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
      <FormError message={errors.root?.server?.message} />
      <div className="sm:col-span-2">
        <FormField
          label="Headline"
          placeholder="e.g. React Native Developer · 3 years"
          registration={register('headline')}
          error={errors.headline}
        />
      </div>
      <FormField label="Phone" type="tel" registration={register('phone')} error={errors.phone} />
      <FormField label="Location" registration={register('location')} error={errors.location} />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="profile-timezone">Time zone</Label>
        <Select id="profile-timezone" {...register('timezone')}>
          {zones.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </Select>
      </div>
      <div />
      <FormField
        label="LinkedIn"
        type="url"
        registration={register('linkedin')}
        error={errors.linkedin}
      />
      <FormField
        label="GitHub"
        type="url"
        registration={register('github')}
        error={errors.github}
      />
      <FormField
        label="Portfolio"
        type="url"
        registration={register('portfolio')}
        error={errors.portfolio}
      />
      <div className="sm:col-span-2">
        <Button type="submit" disabled={isSubmitting || !isDirty}>
          {isSubmitting ? 'Saving…' : 'Save profile'}
        </Button>
      </div>
    </form>
  )
}

export default function ProfilePage() {
  const profile = useProfile()

  return (
    <>
      <PageHeader title="Profile" description="Used in your applications and emails." />
      <div className="flex max-w-3xl flex-col gap-6">
        <NameCard />
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>Contact details and links shown to recruiters.</CardDescription>
          </CardHeader>
          <CardContent>
            {profile.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
            {profile.isError && <FormError message={profile.error.message} />}
            {profile.data && <ProfileForm profile={profile.data} />}
          </CardContent>
        </Card>
        <AccountDataCard />
      </div>
    </>
  )
}
