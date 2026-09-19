/**
 * Auth context — manages current user and token state globally.
 * Optimized: JWT decoded locally for instant restore, then verified in background.
 */
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authApi } from '../services/api'
import type { User } from '../types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isAuthenticated: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

/** Decode JWT payload without verifying signature (for instant local restore) */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const base64 = token.split('.')[1]
    const json = atob(base64.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json)
  } catch {
    return null
  }
}

/** Check if JWT is expired locally (no network needed) */
function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token)
  if (!payload || typeof payload.exp !== 'number') return true
  return Date.now() / 1000 > payload.exp
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')

    // No token — go straight to login immediately (no network call)
    if (!token) {
      setLoading(false)
      return
    }

    // Token expired locally — clear and show login immediately (no network call)
    if (isTokenExpired(token)) {
      localStorage.clear()
      setLoading(false)
      return
    }

    // Token looks valid — restore user from cache instantly (no network call)
    const cachedUser = localStorage.getItem('cached_user')
    if (cachedUser) {
      try {
        setUser(JSON.parse(cachedUser))
        setLoading(false) // Show app immediately from cache!
      } catch {
        // corrupt cache — ignore and fall through to network verify
      }
    }

    // Verify with backend in background (refresh user data silently)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => {
      controller.abort()
      // If we never loaded from cache, force logout on timeout
      if (!cachedUser) {
        localStorage.clear()
        setUser(null)
        setLoading(false)
      }
    }, 5000)

    authApi.me()
      .then(r => {
        setUser(r.data)
        localStorage.setItem('cached_user', JSON.stringify(r.data))
        if (!cachedUser) setLoading(false)
      })
      .catch(() => {
        localStorage.clear()
        setUser(null)
        if (!cachedUser) setLoading(false)
      })
      .finally(() => clearTimeout(timeoutId))

    return () => {
      clearTimeout(timeoutId)
      controller.abort()
    }
  }, [])

  const login = async (email: string, password: string) => {
    const r = await authApi.login(email, password)
    const { access_token, refresh_token, user: u } = r.data
    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)
    localStorage.setItem('cached_user', JSON.stringify(u)) // cache for instant next-visit restore
    setUser(u)
  }

  const logout = async () => {
    try { await authApi.logout() } catch {}
    localStorage.clear()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
