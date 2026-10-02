import { z } from 'zod'

const searchFields = {
  keywords: z
    .string()
    .trim()
    .min(2, 'Enter at least 2 characters.')
    .max(200, 'At most 200 characters.'),
  location: z.string().trim().max(100, 'At most 100 characters.'),
  experience: z.string(),
  remote_only: z.boolean(),
  country: z
    .string()
    .trim()
    .regex(/^[a-zA-Z]{2}$/, 'Use a 2-letter country code, e.g. in, us, gb.'),
}

export const searchSchema = z.object({
  ...searchFields,
  date_posted: z.string(),
  num_pages: z.number().int().min(1).max(3),
})

export const savedSearchSchema = z.object({
  name: z.string().trim().min(1, 'Give the search a name.').max(100, 'At most 100 characters.'),
  ...searchFields,
  schedule: z.string(),
  custom_cron: z.string().trim(),
})

/** Form values → API body (empty strings become null). */
export function toSearchBody(values) {
  return {
    keywords: values.keywords,
    location: values.location || null,
    experience: values.experience || null,
    remote_only: values.remote_only,
    country: values.country.toLowerCase(),
  }
}
