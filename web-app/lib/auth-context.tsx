'use client'

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { authApi } from './api-auth'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  storeTokens,
} from './api'

// ─── Types ────────────────────────────────────────────────────────────────────

interface AuthContextValue {
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  register: (email: string, password: string) => Promise<{ message: string }>
}

// ─── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null)

// ─── Provider ─────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  // On mount: check stored tokens and attempt a refresh if needed
  useEffect(() => {
    async function checkAuth() {
      const accessToken = getAccessToken()
      const refreshToken = getRefreshToken()

      if (accessToken) {
        // Treat the presence of an access token as authenticated
        // (the API interceptor will handle expiry transparently)
        setIsAuthenticated(true)
        setIsLoading(false)
        return
      }

      if (refreshToken) {
        try {
          const { access_token } = await authApi.refresh(refreshToken)
          storeTokens(access_token, refreshToken)
          setIsAuthenticated(true)
        } catch {
          clearTokens()
          setIsAuthenticated(false)
        }
      } else {
        setIsAuthenticated(false)
      }

      setIsLoading(false)
    }

    checkAuth()
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const { access_token, refresh_token } = await authApi.login(email, password)
    storeTokens(access_token, refresh_token)
    setIsAuthenticated(true)
  }, [])

  const logout = useCallback(async () => {
    const accessToken = getAccessToken()
    const refreshToken = getRefreshToken()
    try {
      if (accessToken && refreshToken) {
        await authApi.logout(accessToken, refreshToken)
      }
    } catch {
      // Swallow errors — clear locally regardless
    } finally {
      clearTokens()
      setIsAuthenticated(false)
    }
  }, [])

  const register = useCallback(
    async (email: string, password: string) => {
      return authApi.register(email, password)
    },
    [],
  )

  return (
    <AuthContext.Provider value={{ isLoading, isAuthenticated, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  )
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
