import { diffWords } from '@/lib/diff'

function overlap(a, b) {
  return diffWords(a, b)
    .filter((part) => part.type === 'same')
    .reduce((sum, part) => sum + part.text.split(/\s+/).filter(Boolean).length, 0)
}

/** The master bullet each tailored bullet was most likely rewritten from ('' if none). */
export function closestBullet(bullet, candidates) {
  let best = ''
  let bestScore = 0
  for (const candidate of candidates) {
    const score = overlap(candidate, bullet)
    if (score > bestScore) {
      best = candidate
      bestScore = score
    }
  }
  return best
}

/** Experience entries of the master matched to the tailored ones (by company + title). */
export function matchingJob(job, masterJobs) {
  return (
    masterJobs.find((m) => m.company === job.company && m.title === job.title) ??
    masterJobs.find((m) => m.company === job.company) ??
    null
  )
}

/** Form values ⇄ parsed resume for the editor. */
export function toEditForm(parsed) {
  return {
    summary: parsed.summary ?? '',
    skills: parsed.skills.join(', '),
    highlights: parsed.experience.map((job) => job.highlights.join('\n')),
  }
}

export function fromEditForm(parsed, form) {
  return {
    ...parsed,
    summary: form.summary.trim() || null,
    skills: form.skills
      .split(',')
      .map((skill) => skill.trim())
      .filter(Boolean),
    experience: parsed.experience.map((job, index) => ({
      ...job,
      highlights: (form.highlights[index] ?? '')
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
    })),
  }
}
