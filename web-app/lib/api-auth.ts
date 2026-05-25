import { apiClient } from './api'

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface RefreshResponse {
  access_token: string
  token_type: string
}

export const authApi = {
  async register(email: string, password: string): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>('/api/auth/register', {
      email,
      password,
    })
    return data
  },

  async login(email: string, password: string): Promise<LoginResponse> {
    const { data } = await apiClient.post<LoginResponse>('/api/auth/login', {
      email,
      password,
    })
    return data
  },

  async refresh(refreshToken: string): Promise<RefreshResponse> {
    const { data } = await apiClient.post<RefreshResponse>('/api/auth/refresh', {
      refresh_token: refreshToken,
    })
    return data
  },

  async logout(accessToken: string, refreshToken: string): Promise<void> {
    await apiClient.post('/api/auth/logout', {
      access_token: accessToken,
      refresh_token: refreshToken,
    })
  },
}
