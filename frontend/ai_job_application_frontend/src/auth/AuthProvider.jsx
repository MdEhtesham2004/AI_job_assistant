import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { authApi } from '@/features/auth/api'

import { AuthContext } from './authContext'
import { tokenStore } from './tokenStore'

const ANONYMOUS = { status: 'anonymous', user: null }

export function AuthProvider({ children }) {
  const queryClient = useQueryClient()
  const [state, setState] = useState({ status: 'loading', user: null })

  const applySession = useCallback((session) => {
    tokenStore.set(session.access_token)
    setState({ status: 'authenticated', user: session.user })
    return session.user
  }, [])

  const clearSession = useCallback(() => {
    tokenStore.clear()
    queryClient.clear()
    setState(ANONYMOUS)
  }, [queryClient])

  // Restore the session after a page reload (the access token lives only in memory).
  useEffect(() => {
    let cancelled = false
    authApi
      .refresh()
      .then((session) => !cancelled && applySession(session))
      .catch(() => !cancelled && setState(ANONYMOUS))
    return () => {
      cancelled = true
    }
  }, [applySession])

  // The API client ends the session when a refresh fails (expired, revoked, deactivated).
  useEffect(
    () =>
      tokenStore.onSessionEnded(() => {
        clearSession()
        toast.info('Your session has ended. Please sign in again.')
      }),
    [clearSession],
  )

  const login = useCallback(
    async (values) => applySession(await authApi.login(values)),
    [applySession],
  )

  const register = useCallback(
    async (values) => applySession(await authApi.register(values)),
    [applySession],
  )

  const changePassword = useCallback(
    async (values) => applySession(await authApi.changePassword(values)),
    [applySession],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      clearSession()
    }
  }, [clearSession])

  const reloadUser = useCallback(async () => {
    const user = await authApi.me()
    setState({ status: 'authenticated', user })
    return user
  }, [])

  const value = useMemo(
    () => ({ ...state, login, register, logout, changePassword, reloadUser }),
    [state, login, register, logout, changePassword, reloadUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
