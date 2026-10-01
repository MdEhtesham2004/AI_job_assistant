import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PASSWORD_MIN_LENGTH, registerSchema } from '@/features/auth/schemas'
import { applyServerErrors } from '@/lib/forms'

export default function RegisterPage() {
  const { register: registerAccount } = useAuth()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(registerSchema),
    defaultValues: { full_name: '', email: '', password: '', confirm_password: '' },
  })

  // On success the GuestOnly guard redirects new (pending) accounts to "awaiting approval".
  const onSubmit = async ({ full_name, email, password }) => {
    try {
      await registerAccount({ full_name, email, password })
    } catch (error) {
      if (error?.code === 'EMAIL_TAKEN') {
        setError('email', { type: 'server', message: error.message })
        return
      }
      if (error?.code === 'WEAK_PASSWORD') {
        setError('password', { type: 'server', message: error.message })
        return
      }
      applyServerErrors(error, setError, ['full_name', 'email', 'password'])
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Create account</CardTitle>
        <CardDescription>An admin will approve your account before you can start.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <FormError message={errors.root?.server?.message} />
          <FormField
            label="Full name"
            autoComplete="name"
            registration={register('full_name')}
            error={errors.full_name}
          />
          <FormField
            label="Email"
            type="email"
            autoComplete="email"
            registration={register('email')}
            error={errors.email}
          />
          <FormField
            label="Password"
            type="password"
            autoComplete="new-password"
            hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
            registration={register('password')}
            error={errors.password}
          />
          <FormField
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            registration={register('confirm_password')}
            error={errors.confirm_password}
          />
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Creating account…' : 'Create account'}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  )
}
