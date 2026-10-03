import { z } from 'zod'

// Mirror backend/app/schemas/users.py.
const optionalText = (max, label) =>
  z.string().trim().max(max, `${label} is too long`).optional().or(z.literal(''))

const optionalUrl = z
  .string()
  .trim()
  .refine((value) => value === '' || /^https?:\/\/\S+\.\S+/.test(value), {
    message: 'Enter a full link starting with https://',
  })

export const nameSchema = z.object({
  full_name: z.string().trim().min(1, 'Your name is required').max(120, 'Name is too long'),
})

export const profileSchema = z.object({
  headline: optionalText(220, 'Headline'),
  phone: optionalText(30, 'Phone'),
  location: optionalText(120, 'Location'),
  timezone: z.string().min(1, 'Choose a time zone'),
  linkedin: optionalUrl,
  github: optionalUrl,
  portfolio: optionalUrl,
})

const percent = z.number({ error: 'Enter a number' }).int().min(0, 'Min 0').max(100, 'Max 100')
const range = (min, max) =>
  z.number({ error: 'Enter a number' }).int().min(min, `Min ${min}`).max(max, `Max ${max}`)

export const WEIGHT_FIELDS = [
  ['skills', 'Skills'],
  ['experience', 'Experience'],
  ['technology', 'Technology'],
  ['education', 'Education'],
  ['location', 'Location'],
]

export const settingsSchema = z
  .object({
    threshold_use_master: percent,
    threshold_tailor: percent,
    score_weights: z.object(Object.fromEntries(WEIGHT_FIELDS.map(([key]) => [key, percent]))),
    auto_analyze_new_jobs: z.boolean(),
    daily_send_cap: range(0, 500),
    send_interval_seconds: range(30, 3600),
    recipient_cooldown_days: range(0, 365),
    follow_up_days: range(0, 60),
    no_response_days: range(1, 180),
    linkedin_source_enabled: z.boolean(),
    automation_enabled: z.boolean(),
    automation_min_score: percent,
    // Edited as "React Native, Flutter"; sent as a list (see keywordList).
    automation_keywords: z
      .string()
      .refine((v) => keywordList(v).length <= 5, 'At most 5 keywords')
      .refine((v) => keywordList(v).every((k) => k.length >= 2 && k.length <= 60), {
        message: 'Each keyword needs 2–60 characters',
      }),
    automation_interval_hours: range(6, 168),
    automation_max_jobs: range(1, 20),
    automation_posted_limit: z.enum(['24h', 'week', 'month']),
    automation_tailor: z.boolean(),
    automation_cover_letter: z.boolean(),
    monthly_ai_budget_usd: z.number({ error: 'Enter an amount' }).min(0).max(1000),
  })
  .refine((v) => v.threshold_tailor < v.threshold_use_master, {
    path: ['threshold_tailor'],
    message: 'Must be lower than the "use master resume" threshold',
  })
  .refine((v) => Object.values(v.score_weights).reduce((sum, n) => sum + n, 0) === 100, {
    path: ['score_weights'],
    message: 'Weights must add up to 100',
  })

/** "React Native, flutter ," → ['React Native', 'flutter'] */
export function keywordList(text) {
  return String(text ?? '')
    .split(',')
    .map((k) => k.trim())
    .filter(Boolean)
}

export function timeZones() {
  try {
    return Intl.supportedValuesOf('timeZone')
  } catch {
    return ['Asia/Kolkata', 'UTC']
  }
}
