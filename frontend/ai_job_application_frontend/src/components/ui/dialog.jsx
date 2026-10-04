import { X } from 'lucide-react'
import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'

import { cn } from '@/lib/utils'

/** Minimal accessible modal: Escape and backdrop close it, focus moves inside. */
export function Dialog({ open, onClose, title, description, children, className }) {
  const titleId = useId()
  const descriptionId = useId()
  const panelRef = useRef(null)
  // Keep the latest onClose without re-running the effect: callers usually pass an inline
  // arrow, and re-running moved the focus back to the first field on every keystroke
  // (found in Phase 14: typing a password jumped to the email field).
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement
    const focusable = panelRef.current?.querySelector(
      'input, textarea, select, button:not([data-dialog-close])',
    )
    focusable?.focus()
    const onKeyDown = (event) => event.key === 'Escape' && onCloseRef.current()
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus?.()
    }
  }, [open])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className={cn(
          'relative w-full max-w-md rounded-xl border bg-card p-5 text-card-foreground shadow-xl',
          className,
        )}
      >
        <button
          type="button"
          data-dialog-close
          onClick={onClose}
          className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-accent"
          aria-label="Close"
        >
          <X className="size-4" />
        </button>
        <h2 id={titleId} className="pr-8 text-base font-semibold">
          {title}
        </h2>
        {description && (
          <p id={descriptionId} className="mt-1 text-sm text-muted-foreground">
            {description}
          </p>
        )}
        <div className="mt-4">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
