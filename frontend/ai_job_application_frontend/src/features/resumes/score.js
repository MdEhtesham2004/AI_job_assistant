/** Colour for an ATS score: ≥75 good, ≥50 fair, below that weak. */
export function scoreTone(score) {
  if (score >= 75) return 'success'
  if (score >= 50) return 'warning'
  return 'destructive'
}

export const TONE_TEXT = {
  success: 'text-success',
  warning: 'text-warning',
  destructive: 'text-destructive',
}

export const TONE_BG = {
  success: 'bg-success',
  warning: 'bg-warning',
  destructive: 'bg-destructive',
}
