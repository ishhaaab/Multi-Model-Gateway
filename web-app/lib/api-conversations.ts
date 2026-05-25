import { apiClient } from './api'

export interface Conversation {
  id: string
  title: string
  created_at: string
  token_count: number
}

export interface Message {
  id?: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
  model_used?: string | null
}

export const conversationsApi = {
  async list(): Promise<Conversation[]> {
    const { data } = await apiClient.get<Conversation[]>('/api/v1/convo')
    return data
  },

  async create(title: string): Promise<{ id: string }> {
    const { data } = await apiClient.post<{ id: string }>('/api/v1/convo', { title })
    return data
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/convo/${id}`)
  },

  async rename(id: string, title: string): Promise<void> {
    await apiClient.patch(`/api/v1/convo/${id}`, { title })
  },

  async getMessages(id: string): Promise<Message[]> {
    const { data } = await apiClient.get<Message[]>(`/api/v1/convo/${id}`)
    return data
  },
}
