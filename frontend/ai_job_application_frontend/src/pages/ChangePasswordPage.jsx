import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import { useAuth } from '@/auth/useAuth'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { PASSWORD_MIN_LENGTH, changePasswordSchema } from '@/features/auth/schemas'
import { applyServerErrors } from '@/lib/forms'

const EMPTY = { current_password: '', new_password: '', confirm_password: '' }

export default function ChangePasswordPage() {
  const { changePassword } = useAuth()
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(changePasswordSchema), defaultValues: EMPTY })

  const onSubmit = async ({ current_password, new_password }) => {
    try {
      await changePassword({ current_password, new_password })
      reset(EMPTY)
      toast.success('Password changed. Other devices have been signed out.')
    } catch (error) {
      if (error?.code === 'INVALID_CURRENT_PASSWORD') {
        setError('current_password', { type: 'server', message: error.message })
        return
      }
      if (error?.code === 'WEAK_PASSWORD') {
        setError('new_password', { type: 'server', message: error.message })
        return
      }
      applyServerErrors(error, setError, ['current_password', 'new_password'])
    }
  }

  return (
    <>
      <PageHeader
        title="Change password"
        description="Changing your password signs you out on all other devices."
      />
      <Card className="max-w-md">
        <CardContent className="pt-5">
          <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <FormError message={errors.root?.server?.message} />
            <FormField
              label="Current password"
              type="password"
              autoComplete="current-password"
              registration={register('current_password')}
              error={errors.current_password}
            />
            <FormField
              label="New password"
              type="password"
              autoComplete="new-password"
              hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
              registration={register('new_password')}
              error={errors.new_password}
            />
            <FormField
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              registration={register('confirm_password')}
              error={errors.confirm_password}
            />
            <Button type="submit" disabled={isSubmitting} className="self-start">
              {isSubmitting ? 'Saving…' : 'Change password'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </>
  )
}
