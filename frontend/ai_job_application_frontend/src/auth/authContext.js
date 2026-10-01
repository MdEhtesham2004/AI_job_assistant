import { createContext } from 'react'

/**
 * status: 'loading' (restoring the session) | 'authenticated' | 'anonymous'
 * user:   the signed-in user (UserRead from the API) or null
 */
export const AuthContext = createContext(null)
