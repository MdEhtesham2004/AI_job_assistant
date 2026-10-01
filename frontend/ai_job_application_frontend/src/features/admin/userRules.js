/** Deactivation wins over the approval status (same rule as the backend filter). */
export function userStatus(user) {
  return user.is_active ? user.approval_status : 'deactivated'
}

/** Which actions a row offers. The backend enforces the same rules. */
export function availableActions(user, currentUserId) {
  if (user.id === currentUserId) return []
  const status = userStatus(user)
  const actions = []
  if (status === 'pending') actions.push('approve', 'reject')
  if (status === 'rejected') actions.push('approve')
  if (status === 'approved' && user.role === 'user') actions.push('makeAdmin')
  if (status === 'approved' && user.role === 'admin') actions.push('removeAdmin')
  actions.push(user.is_active ? 'deactivate' : 'reactivate')
  return actions
}
