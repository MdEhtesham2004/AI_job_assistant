import { Check, ShieldCheck, ShieldOff, UserMinus, UserPlus, X } from 'lucide-react'

import { Button } from '@/components/ui/button'

import { availableActions } from '../userRules'

const BUTTONS = {
  approve: { label: 'Approve', icon: Check, variant: 'default' },
  reject: { label: 'Reject', icon: X, variant: 'outline' },
  makeAdmin: { label: 'Make admin', icon: ShieldCheck, variant: 'ghost' },
  removeAdmin: { label: 'Remove admin', icon: ShieldOff, variant: 'ghost' },
  deactivate: { label: 'Deactivate', icon: UserMinus, variant: 'ghost' },
  reactivate: { label: 'Reactivate', icon: UserPlus, variant: 'ghost' },
}

export function UserRowActions({ user, currentUserId, disabled, onAction }) {
  const actions = availableActions(user, currentUserId)
  if (actions.length === 0) {
    return <span className="text-xs text-muted-foreground">This is you</span>
  }
  return (
    <div className="flex flex-wrap justify-end gap-1">
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
