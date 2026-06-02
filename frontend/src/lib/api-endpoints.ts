import { apiClient } from "./api-client";
import type {
  LoginResponse,
  RefreshResponse,
  Conversation,
  ConvoCreateResponse,
  Message,
  Preset,
  PresetCreate,
  PresetUpdate,
  PromptTemplate,
  TemplateCreate,
  TemplateUpdate,
  RewriteResponse,
  ImageGenerateRequest,
  ImageGenerateResponse,
  ImageStatusResponse,
  ListEnvelope,
  LocalModel,
  OpenRouterListResponse,
} from "./types";

// ───────────── Auth ─────────────
export const authApi = {
  register: (email: string, password: string) =>
    apiClient.request<{ message: string }>("POST", "/auth/register", { email, password }),

  login: (email: string, password: string) =>
    apiClient.request<LoginResponse>("POST", "/auth/login", { email, password }),

  refresh: (refreshToken: string) =>
    apiClient.request<RefreshResponse>("POST", "/auth/refresh", {
      refresh_token: refreshToken,
    }),

  logout: (refreshToken: string) =>
    apiClient.request<{ message: string }>("POST", "/auth/logout", {
      refresh_token: refreshToken,
    }),
};

// ───────────── Conversations (bare arrays) ─────────────
export const convoApi = {
  list: () => apiClient.request<Conversation[]>("GET", "/v1/convo"),

  create: (title: string) =>
    apiClient.request<ConvoCreateResponse>("POST", "/v1/convo", { title }),

  getMessages: (id: string) =>
    apiClient.request<Message[]>("GET", `/v1/convo/${id}`),

  rename: (id: string, title: string) =>
    apiClient.request<{ message: string }>("PATCH", `/v1/convo/${id}`, { title }),

  delete: (id: string) =>
    apiClient.request<{ message: string }>("DELETE", `/v1/convo/${id}`),
};

// ───────────── Presets ({ data: [...] }) ─────────────
export const presetApi = {
  list: () => apiClient.request<ListEnvelope<Preset>>("GET", "/v1/presets"),

  get: (id: string) => apiClient.request<Preset>("GET", `/v1/presets/${id}`),

  create: (data: PresetCreate) =>
    apiClient.request<Preset>("POST", "/v1/presets", data),

  update: (id: string, data: PresetUpdate) =>
    apiClient.request<Preset>("PATCH", `/v1/presets/${id}`, data),

  delete: (id: string) =>
    apiClient.request<{ detail: string }>("DELETE", `/v1/presets/${id}`),
};

// ───────────── Templates ({ data: [...] }) ─────────────
export const templateApi = {
  list: () => apiClient.request<ListEnvelope<PromptTemplate>>("GET", "/v1/templates"),

  get: (id: string) =>
    apiClient.request<PromptTemplate>("GET", `/v1/templates/${id}`),

  create: (data: TemplateCreate) =>
    apiClient.request<PromptTemplate>("POST", "/v1/templates", data),

  update: (id: string, data: TemplateUpdate) =>
    apiClient.request<PromptTemplate>("PATCH", `/v1/templates/${id}`, data),

  delete: (id: string) =>
    apiClient.request<{ detail: string }>("DELETE", `/v1/templates/${id}`),

  rewrite: (prompt: string, templateId?: string | null) =>
    apiClient.request<RewriteResponse>("POST", "/v1/templates/rewrite", {
      prompt,
      template_id: templateId ?? null,
    }),
};

// ───────────── Images ─────────────
export const imageApi = {
  generate: (data: ImageGenerateRequest) =>
    apiClient.request<ImageGenerateResponse>("POST", "/v1/images/generate", data),

  status: (promptId: string) =>
    apiClient.request<ImageStatusResponse>("GET", `/v1/images/status/${promptId}`),
};

// ───────────── Models ─────────────
export const modelApi = {
  listLocal: () => apiClient.request<ListEnvelope<LocalModel>>("GET", "/v1/models"),

  listOpenRouter: () =>
    apiClient.request<OpenRouterListResponse>("GET", "/v1/openrouter/models"),

  health: () => apiClient.request<{ status: string }>("GET", "/health"),
};
