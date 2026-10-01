import { z } from 'zod'

// Must match the backend (app/schemas/auth.py).
export const PASSWORD_MIN_LENGTH = 10
export const PASSWORD_MAX_LENGTH = 128

const email = z.string().trim().min(1, 'Email is required').email('Enter a valid email address')

const newPassword = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Use at least ${PASSWORD_MIN_LENGTH} characters`)
  .max(PASSWORD_MAX_LENGTH, `Use at most ${PASSWORD_MAX_LENGTH} characters`)

export const loginSchema = z.object({
  email,
  password: z.string().min(1, 'Password is required'),
})

export const registerSchema = z
  .object({
    full_name: z.string().trim().min(1, 'Your name is required').max(120, 'Name is too long'),
    email,
    password: newPassword,
    confirm_password: z.string(),
  })
  .refine((values) => values.password === values.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  })

export const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, 'Current password is required'),
    new_password: newPassword,
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  })
  .refine((values) => values.new_password !== values.current_password, {
    path: ['new_password'],
    message: 'Choose a password different from the current one',
  })
