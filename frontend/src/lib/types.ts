// ============================================================
// Types mirror the FastAPI backend (the source of truth).
// Verified against backend/app/routers/* and backend/app/models/*.
// ============================================================

// ───────────── Auth ─────────────
export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type Provider = "auto" | "local" | "openrouter";

// ───────────── Chat ─────────────
export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatRequest {
  conversation_id: string | null;
  preset_id: string | null;
  messages: ChatMessage[];
  // The backend only performs "auto" routing when model === "auto";
  // otherwise it pins the given model. Default to "auto".
  model?: string;
  stream?: boolean;
  provider?: Provider;
  private?: boolean;
}

// ───────────── Conversations ─────────────
export interface Conversation {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  token_count: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  model_used: string | null;
  tokens_used: number | null;
  index: number | null;
}

// POST /v1/convo → { message, id }
export interface ConvoCreateResponse {
  message: string;
  id: string;
}

// ───────────── Presets ─────────────
export interface Preset {
  id: string;
  user_id: string;
  name: string;
  system_prompt: string | null;
  temperature: number;
  token_limit: number | null;
  context_overflow: string | null;
  stop_strings: string[] | null;
  top_k: number | null;
  top_p: number | null;
  min_p: number | null;
  repeat_penalty: number | null;
  created_at: string;
}

export interface PresetCreate {
  name: string;
  system_prompt?: string | null;
  temperature?: number;
  token_limit?: number | null;
  context_overflow?: string | null;
  stop_strings?: string[] | null;
  top_k?: number | null;
  top_p?: number | null;
  min_p?: number | null;
  repeat_penalty?: number | null;
}

export type PresetUpdate = Partial<PresetCreate>;

// ───────────── Templates ─────────────
export interface PromptTemplate {
  id: string;
  user_id: string;
  name: string;
  description: string;
  structure: string;
  created_at: string;
}

export interface TemplateCreate {
  name: string;
  description: string;
  structure: string;
}

export type TemplateUpdate = Partial<TemplateCreate>;

export interface RewriteRequest {
  prompt: string;
  template_id?: string | null;
}

export interface RewriteResponse {
  rewritten_prompt: string;
}

// ───────────── Images ─────────────
export interface ImageGenerateRequest {
  prompt: string;
  negative_prompt?: string;
  template_id?: string | null;
  steps?: number;
  cfg?: number;
  aspect_ratio?: string;
  batch_size?: number;
  seed?: number | null;
  rewrite?: boolean;
}

export interface ImageGenerateResponse {
  prompt_id: string;
  rewritten_prompt: string;
}

export interface ImageResult {
  filename: string;
  url: string;
}

export interface ImageStatusResponse {
  status: "pending" | "complete";
  images?: ImageResult[];
}

// GET /v1/images/aspect-ratios — backend is the single source of truth for the
// ResolutionSelector node's valid values.
export interface AspectRatiosResponse {
  aspect_ratios: string[];
  default: string;
}

// ───────────── Models ─────────────
export interface LocalModel {
  id: string;
  object: string;
}

export interface OpenRouterModel {
  id: string;
  name: string;
  context_length: number | null;
  description: string;
}

// ───────────── List envelopes ─────────────
// NOTE: presets & templates lists are wrapped in { data: [...] };
// conversations & messages are returned as BARE arrays.
export interface ListEnvelope<T> {
  data: T[];
}

export interface OpenRouterListResponse {
  data: OpenRouterModel[];
  count: number;
}
