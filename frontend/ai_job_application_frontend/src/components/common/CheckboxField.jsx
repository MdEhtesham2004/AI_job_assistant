import { useId } from 'react'

export function CheckboxField({ label, description, registration, ...props }) {
  const id = useId()
  return (
    <div className="flex items-start gap-3">
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 size-4 rounded border accent-primary"
        {...registration}
        {...props}
      />
      <label htmlFor={id} className="text-sm">
        <span className="font-medium">{label}</span>
        {description && <span className="block text-muted-foreground">{description}</span>}
      </label>
    </div>
  )
}
