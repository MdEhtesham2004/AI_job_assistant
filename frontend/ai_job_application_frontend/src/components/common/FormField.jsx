import { useId } from 'react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/** Label + input + validation message, wired for react-hook-form's `register`. */
export function FormField({ label, error, hint, registration, ...inputProps }) {
  const id = useId()
  const messageId = `${id}-message`
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={error || hint ? messageId : undefined}
        {...registration}
        {...inputProps}
      />
      {error ? (
        <p id={messageId} className="text-xs text-destructive">
          {error.message}
        </p>
      ) : (
        hint && (
          <p id={messageId} className="text-xs text-muted-foreground">
            {hint}
          </p>
        )
      )}
    </div>
  )
}
