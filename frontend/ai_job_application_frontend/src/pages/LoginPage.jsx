import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { loginSchema } from '@/features/auth/schemas'
import { applyServerErrors } from '@/lib/forms'

export default function LoginPage() {
  const { login } = useAuth()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(loginSchema), defaultValues: { email: '', password: '' } })

  // On success the GuestOnly guard redirects (back to the original page, or "awaiting approval").
  const onSubmit = async (values) => {
    try {
      await login(values)
    } catch (error) {
      applyServerErrors(error, setError, ['email', 'password'])
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Sign in</CardTitle>
        <CardDescription>Welcome back. Enter your email and password.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <FormError message={errors.root?.server?.message} />
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
            autoComplete="current-password"
            registration={register('password')}
            error={errors.password}
          />
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            No account yet?{' '}
            <Link to="/register" className="font-medium text-primary hover:underline">
              Create one
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  )
}
