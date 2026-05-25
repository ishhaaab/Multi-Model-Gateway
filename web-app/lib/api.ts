import axios, { AxiosInstance, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios'

// ─── Token helpers ────────────────────────────────────────────────────────────

const ACCESS_TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function updateAccessToken(token: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(ACCESS_TOKEN_KEY, token)
}

export function storeTokens(accessToken: string, refreshToken: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

export function clearTokens(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

// ─── Axios instance ───────────────────────────────────────────────────────────

export const apiClient: AxiosInstance = axios.create({
  baseURL: '',   // same origin — Next.js rewrites proxy to backend
  headers: { 'Content-Type': 'application/json' },
})

// ─── Request interceptor: attach Bearer token ─────────────────────────────────

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// ─── Response interceptor: auto-refresh on 401 ───────────────────────────────

let isRefreshing = false
let refreshQueue: Array<{
  resolve: (token: string) => void
  reject: (err: unknown) => void
}> = []

function processQueue(error: unknown, token: string | null) {
  refreshQueue.forEach((p) => {
    if (error) p.reject(error)
    else p.resolve(token!)
  })
  refreshQueue = []
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }

    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error)
    }

    const refreshToken = getRefreshToken()
    if (!refreshToken) {
      clearTokens()
      if (typeof window !== 'undefined') window.location.href = '/login'
      return Promise.reject(error)
    }

    if (isRefreshing) {
      // Queue the request until refresh completes
      return new Promise<string>((resolve, reject) => {
        refreshQueue.push({ resolve, reject })
      }).then((newToken) => {
        originalRequest.headers = {
          ...(originalRequest.headers ?? {}),
          Authorization: `Bearer ${newToken}`,
        }
        originalRequest._retry = true
        return apiClient(originalRequest)
      })
    }

    originalRequest._retry = true
    isRefreshing = true

    try {
      const { data } = await axios.post<{ access_token: string }>('/api/auth/refresh', {
        refresh_token: refreshToken,
      })
      const newToken = data.access_token
      updateAccessToken(newToken)
      processQueue(null, newToken)

      originalRequest.headers = {
        ...(originalRequest.headers ?? {}),
        Authorization: `Bearer ${newToken}`,
      }
      return apiClient(originalRequest)
    } catch (refreshError) {
      processQueue(refreshError, null)
      clearTokens()
      if (typeof window !== 'undefined') window.location.href = '/login'
      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  },
)
