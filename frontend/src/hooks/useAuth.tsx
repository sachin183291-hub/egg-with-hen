/**
 * Auth context — manages current user and token state globally.
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      // No token stored — go straight to login, no network call needed
      setLoading(false)
      return
    }

    // Fast timeout (5s) — if backend is slow/offline, show login immediately
    const controller = new AbortController()
    const timeoutId = setTimeout(() => {
      controller.abort()
      localStorage.clear()
      setUser(null)
      setLoading(false)
    }, 5000)

    authApi.me()
      .then(r => setUser(r.data))
      .catch(() => { localStorage.clear(); setUser(null) })
      .finally(() => {
        clearTimeout(timeoutId)
        setLoading(false)
      })

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
