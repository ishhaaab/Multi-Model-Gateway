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
  // Branch lineage: set when this conversation was forked from another.
  parent_id: string | null;
  branched_from_message_id: string | null;
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

// ───────────── Providers (BYO-key) ─────────────
export type ProviderType =
  | "openai_compatible"
  | "openai"
  | "anthropic"
  | "google"
  | "openrouter";

export type ProviderRole = "local" | "cloud";

export interface ProviderRow {
  id: string;
  name: string;
  type: ProviderType;
  role: ProviderRole;
  base_url?: string | null;
  default_model?: string | null;
  is_default: boolean;
  enabled: boolean;
  created_at: string;
  api_key_masked: string;
}

export interface ProviderCreate {
  name: string;
  type: ProviderType;
  role: ProviderRole;
  base_url?: string | null;
  api_key?: string | null;
  default_model?: string | null;
  is_default?: boolean;
  enabled?: boolean;
}

export interface ProviderUpdate {
  name?: string;
  type?: ProviderType;
  role?: ProviderRole;
  base_url?: string | null;
  api_key?: string | null;
  default_model?: string | null;
  is_default?: boolean;
  enabled?: boolean;
}

export interface ProviderTestResult {
  ok: boolean;
  model?: string | null;
  error?: string | null;
}

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

export interface Workflow {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  graph: Record<string, unknown>;
  param_map: Record<string, unknown> | null;
  created_at: string;
}

export interface WorkflowCreate {
  name: string;
  description?: string | null;
  graph: Record<string, unknown>;
  param_map?: Record<string, unknown> | null;
}

export type WorkflowUpdate = Partial<WorkflowCreate>;

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
  workflow_id?: string | null;
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

// ───────────── Agents / MCP ─────────────
export interface AgentToolInfo {
  name: string;
  description: string;
  first_party: boolean;
  allowed: boolean;
}

// SSE events from POST /v1/agent/chat (one JSON object per `data:` line).
export type AgentEvent =
  | { type: "tool_call"; id: string; name: string; arguments: string }
  | { type: "tool_result"; id: string; name: string; content: string }
  | { type: "token"; content: string }
  | { type: "error"; message: string }
  | { type: "done"; conversation_id: string };

// ───────────── Deep Research ─────────────
export type ResearchStatus =
  | "queued"
  | "running"
  | "complete"
  | "cancelled"
  | "error"
  | "failed";

export interface ResearchSource {
  n: number;
  title: string;
  url: string;
}

// List item (GET /v1/research)
export interface ResearchJob {
  id: string;
  query: string;
  status: ResearchStatus;
  stage: string | null;
  progress: number | null;
  created_at: string;
}

// Full job (GET /v1/research/{id})
export interface ResearchJobDetail extends ResearchJob {
  result: string | null;
  sources: ResearchSource[] | null;
  error: string | null;
}

export interface ResearchCreateResponse {
  job_id: string;
  status: ResearchStatus;
}

// SSE events from GET /v1/research/{id}/stream.
export type ResearchEvent =
  | { type: "progress"; stage: string; progress: number; message: string }
  | { type: "done"; status: "complete"; result: string; sources: ResearchSource[] }
  | { type: "done"; status: "cancelled" }
  | { type: "error"; message: string };

// ───────────── Cookbook / Hardware ─────────────
export interface GpuInfo {
  index: number;
  name: string;
  vram_total_mb: number;
  vram_free_mb: number;
}

export interface HardwareInfo {
  gpu_available: boolean;
  gpus: GpuInfo[];
}

export type CookbookVerdict =
  | "fits_fully"
  | "partial_offload"
  | "wont_fit"
  | "cpu_only"
  | "unknown";

export interface CookbookModel {
  id: string;
  source: string;
  params_b: number;
  quant: string;
  verdict: CookbookVerdict;
  score: number;
  need_gb: number;
  rationale: string;
}

export interface CookbookResponse {
  hardware: HardwareInfo;
  context_tokens: number;
  recommendation: string;
  models: CookbookModel[];
}
