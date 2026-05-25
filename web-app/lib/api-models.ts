import { apiClient } from './api'

export interface LocalModel {
  id: string
}

export interface OpenRouterModel {
  id: string
  name: string
}

export const modelsApi = {
  async getLocalModels(): Promise<{ data: LocalModel[] }> {
    const { data } = await apiClient.get<{ data: LocalModel[] }>('/api/v1/models')
    return data
  },

  async getOpenRouterModels(): Promise<{ data: OpenRouterModel[] }> {
    const { data } = await apiClient.get<{ data: OpenRouterModel[] }>('/api/v1/openrouter/models')
    return data
  },
}
