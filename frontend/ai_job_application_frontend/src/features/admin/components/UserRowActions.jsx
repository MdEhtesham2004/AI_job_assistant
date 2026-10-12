import { Check, Mail, MailX, ShieldCheck, ShieldOff, UserMinus, UserPlus, X } from 'lucide-react'

import { Button } from '@/components/ui/button'

import { availableActions, userStatus } from '../userRules'

const BUTTONS = {
  approve: { label: 'Approve', icon: Check, variant: 'default' },
  reject: { label: 'Reject', icon: X, variant: 'outline' },
  makeAdmin: { label: 'Make admin', icon: ShieldCheck, variant: 'ghost' },
  removeAdmin: { label: 'Remove admin', icon: ShieldOff, variant: 'ghost' },
  deactivate: { label: 'Deactivate', icon: UserMinus, variant: 'ghost' },
  reactivate: { label: 'Reactivate', icon: UserPlus, variant: 'ghost' },
  // Phase 19: per-user permission for scheduled recruiter-email (LinkedIn) searches.
  allowEmailSearches: { label: 'Allow scheduled email searches', icon: Mail, variant: 'ghost' },
  stopEmailSearches: { label: 'Stop scheduled email searches', icon: MailX, variant: 'ghost' },
}

export function UserRowActions({ user, currentUserId, disabled, onAction }) {
  const actions = availableActions(user, currentUserId)
  if (userStatus(user) === 'approved') {
    actions.push(user.linkedin_schedule_allowed ? 'stopEmailSearches' : 'allowEmailSearches')
  }
  return (
    <div className="flex flex-wrap items-center justify-end gap-1">
      {user.id === currentUserId && (
        <span className="text-xs text-muted-foreground">This is you</span>
      )}
      {actions.map((action) => {
        const { label, icon: Icon, variant } = BUTTONS[action]
        return (
          <Button
            key={action}
            size="sm"
            variant={variant}
            disabled={disabled}
            onClick={() => onAction(action, user)}
            aria-label={`${label} ${user.full_name}`}
          >
            <Icon />
            {label}
          </Button>
        )
      })}
    </div>
  )
}
