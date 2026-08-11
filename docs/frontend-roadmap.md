# Frontend Roadmap — Native Mobile App (Expo / React Native)

## Context

The backend is a self-hosted inference gateway (LM Studio chat, ComfyUI images, OpenRouter,
agent + deep research) reached from a phone over Tailscale. The existing React/Vite web frontend
(`frontend/`) works but isn't the right form factor — the goal is a **native mobile app**. This
roadmap builds a new Expo/React Native app in a `mobile/` directory that replaces the web
frontend as the primary client. The web frontend stays as-is for reference/desktop.

**Decisions settled:**
- **Stack: Expo + React Native + TypeScript.** Reuses existing TS knowledge and ports the API
  contract layer (types, SSE parsing, Zustand stores) from the web app.
- **Platform: Android-first.** iOS can follow from the same codebase.
- **Scope: full feature parity.** Chat + agent + research (as in-chat modes) + image generation
  + presets/templates/workflows + cookbook + settings + auth.
- **IA:** Chat ↔ Image are the two primary surfaces (bottom tabs). Agent + Deep Research are
  **modes of chat** (a toggle in the composer). Presets/templates/workflows are config screens.
  Cookbook is a utility under settings.
- **Self-hosting/onboarding is not a concern.** The app talks to one known gateway URL entered
  once on first launch.
- **Polish level: simple, clean, native.** Favor Expo built-in components, minimal custom
  animation, one dark theme.

## Backend contract additions (from backend Phase 1 + 1b)

The backend now supports **bring-your-own-key providers** — user-configured provider rows with
encrypted keys, routed through the same chat/agent/research paths with a legacy env-var
fallback. The contract additions the mobile app must handle:

- **New endpoints (plain JSON CRUD, no SSE):**
  - `GET /v1/providers` — list this user's providers (seeds the default env-based rows on
    first visit if none exist).
  - `POST /v1/providers` — create (name, type, role, base_url, api_key, default_model,
    is_default, enabled).
  - `PATCH /v1/providers/{id}` — update (api_key `null`/omitted = leave unchanged).
  - `DELETE /v1/providers/{id}`.
  - `POST /v1/providers/{id}/test` — one-token round-trip; returns `{ok, model}` or
    `{ok: false, error}`.
- **`ProviderOut` shape:** `id`, `name`, `type` (`openai_compatible|openai|anthropic|google|openrouter`),
  `role` (`local|cloud`), `base_url`, `default_model`, `is_default`, `enabled`, `created_at`,
  `api_key_masked`. Keys are **write-only** — responses never contain plaintext, only a masked
  suffix.
- **`ChatRequest`** (shared by `/v1/chat/completions` AND `/v1/agent/chat`) now accepts an
  optional **`provider_id`** to pin a specific configured provider row (overrides all routing
  heuristics).
- **Routing** now prefers configured provider rows (per-role defaults), falling back to the
  legacy env-var clients when no rows exist. Seeding is **idempotent**: missing rows are
  created on registration and again on the first providers page visit (existing rows are never
  touched). A "Local (LM Studio)" row is seeded when `LM_URL` is configured; an "OpenRouter"
  row is seeded **only** when an OpenRouter API key is configured (no key => no OpenRouter row).
- **OpenAI-compatible `base_url` normalization:** the adapter automatically appends `/v1` when
  the URL doesn't already contain it (e.g. `http://host:1234` becomes `http://host:1234/v1`),
  so user-entered and seeded URLs work without a manual `/v1` suffix.
- **Anthropic + Google adapters** exist for plain chat but do **not** support tool calling yet
  (agent mode is limited to OpenAI-wire providers: openai_compatible / openai / openrouter).
- **Mobile/web implications:**
  - Add a **"Providers" settings screen** (list/add/edit/delete + test button; fields above;
    masked key display; key input write-only).
  - Optionally a **provider picker in the chat composer** that sends `provider_id` alongside
    the existing preset/mode controls.
  - Update the ported `types.ts` / `api-endpoints.ts` with the provider endpoints and
    `ChatRequest.provider_id`.

### Training (image LoRA fine-tuning, backend Phase 6)

The backend now lets users train image LoRAs from a zip of images and use the result on
image generation. New endpoints:

- `POST /v1/trainings` — multipart form: `name`, `base_model` (`flux-dev` | `sdxl` | `sd1`),
  `dataset` (zip of 3+ images; optional `{image}.txt` captions ride along), `steps`
  (default 1000), `learning_rate` (default 1e-4), `resolution` (default 1024, or 512 for
  `sd1`; the training width=height in pixels, 256–2048 — lower it like 512 for small GPUs,
  FLUX and SD1 are capped at 1024 server-side). Returns `{job_id, status: "queued"}`.
- `GET /v1/trainings` — list this user's jobs (newest first, capped at 50).
- `GET /v1/trainings/{id}` — detail; 404 for missing or foreign jobs.
- `POST /v1/trainings/{id}/cancel` — sets a Redis flag the trainer checks between steps.
- `GET /v1/trainings/{id}/stream` — SSE of `{"type":"progress"|"done"|"error"}` events on
  channel `train:{id}`; `progress` carries `stage` + 0-100 `progress`; `done` carries
  `artifact_filename` (and `sample_image` when complete).
- `GET /v1/trainings/{id}/artifact` — downloads the trained `.safetensors`.

**`TrainingJob` summary shape** (list items; detail adds `dataset_dir`, `params`,
`sample_image`): `id`, `name`, `base_model`, `status` (`queued|running|complete|failed|cancelled`),
`stage`, `progress`, `created_at`, `artifact_filename`, `sample_image`, `error`.

**`ImageRequest`** now accepts `training_id` — uses a trained LoRA from a completed job
(the backend injects a ComfyUI `LoraLoader` node). Requires `COMFY_LORA_DIR` (host folder)
+ `COMFY_LORA_CONTAINER_PATH` (container path the backend writes to) configured server-side;
errors: 404 unknown/foreign job, 409 job not complete, 400 `COMFY_LORA_DIR` unset. The
generate response gains `"lora"` (the filename ComfyUI loaded).

- **Mobile implications:**
  - Add a **"Train" screen**: upload an image zip (`expo-document-picker`), pick base
    model + steps + learning rate + resolution, show a progress card driven by the SSE
    stream (stage + progress bar), and a link to download/open the artifact when `done`
    arrives.
  - Add a **trained-LoRA picker on the image generation screen**: `GET /v1/trainings`
    filtered to `status == "complete"`, send the chosen job id as `training_id` on
    generate; surface the 400/404/409 error strings verbatim.
  - Port the new endpoints into `api-endpoints.ts` / `types.ts`; the SSE stream uses the
    same `streamEvents` helper as research.

## Phases

### Phase 1 — Scaffold + contract layer + auth

1. **Create the Expo project:** `npx create-expo-app@latest mobile --template tabs` (Expo SDK
   52+, Expo Router, TypeScript).
2. **Dependencies:** `zustand`, `react-native-sse` (SSE client for RN — replaces the web app's
   `fetch`+`ReadableStream`), `expo-secure-store` (JWT storage), `@react-native-async-storage/async-storage`
   (gateway URL + image history), `react-native-markdown-display`, `lucide-react-native`,
   `expo-haptics`, `expo-web-browser`, `expo-media-library`.
3. **Port types verbatim:** copy `frontend/src/lib/types.ts` (308 lines, pure TypeScript
   interfaces mirroring the backend) to `mobile/src/lib/types.ts`.
4. **Port + adapt the API client:** `mobile/src/lib/api-client.ts` from
   `frontend/src/lib/api-client.ts` (333 lines):
   - Config from AsyncStorage instead of `import.meta.env.VITE_*`; `API_PREFIX` always `/api`.
   - Non-streaming `fetch` ports directly (401-refresh-retry + `ApiError` + refresh coalescing
     carry over); swap `localStorage` → `expo-secure-store`.
   - **SSE:** replace `streamChat()` + `streamEvents()` with `react-native-sse`'s `EventSource`.
     The parsing logic (split on `\n\n`, `data:` prefix, `[DONE]`, `[ERROR]`) ports as-is;
     `EventSource` delivers `e.data` as the payload string. Signatures stay:
     `streamChat(body, onToken, onDone, onError, signal?)` and
     `streamEvents<T>(method, path, body?, signal?): AsyncGenerator<T>`.
   - Pre-flight token check before opening SSE (RN's `EventSource` doesn't expose HTTP status,
     so no mid-stream 401-retry).
   - Port `getImageDisplayUrl()`, `aspectRatioShort()`, `formatRelativeTime()`, `isTokenExpired()`,
     `getProviderInfo()` from `frontend/src/lib/utils.ts`.
5. **Port endpoint definitions:** copy `frontend/src/lib/api-endpoints.ts` verbatim (thin
   wrappers around `apiClient.request()`).
6. **Port Zustand stores:** `auth-store` (SecureStore instead of localStorage), `chat-store`,
   `preset/template/workflow/research/model/agent/ui-stores` (verbatim), `image-store`
   (AsyncStorage instead of localStorage). Drop `layout-store` (no resizable panels on mobile).
7. **Gateway URL config:** `mobile/src/lib/gateway-config.ts` — `getGatewayUrl()` /
   `setGatewayUrl()` in AsyncStorage. First launch shows an onboarding screen with a single
   text input; "Connect" pings `GET /health`.
8. **Auth screens:** `mobile/app/(auth)/login.tsx` + `register.tsx`, adapting the web pages.
   `initializeAuth()` silently refreshes on app open.
9. **Navigation shell** (Expo Router, file-based in `mobile/app/`):
   ```
   _layout.tsx          → root Stack [onboarding → (auth) → (tabs)]
   onboarding.tsx
   (auth)/_layout.tsx, login.tsx, register.tsx
   (tabs)/_layout.tsx   → bottom tabs: Chat, Images, Settings
     (chat)/index.tsx       → conversation list
     (chat)/[id].tsx        → chat thread
     (images)/index.tsx     → image generation + history
     (settings)/index.tsx   → settings menu
     (settings)/presets.tsx, templates.tsx, workflows.tsx, cookbook.tsx, agent-tools.tsx, gateway.tsx
   ```

### Phase 2 — Chat (with agent + research as modes)

10. **Conversation list:** `FlatList` of conversations, tap to open, "New Chat" header button,
    pull-to-refresh, swipe-to-delete.
11. **Chat thread:** inverted `FlatList` of `MessageBubble`s (markdown via
    `react-native-markdown-display`), streaming content appends to the last assistant bubble.
    Composer: auto-growing `TextInput` + send/stop button + **mode segmented control**
    (Chat / Agent / Research) + preset dropdown + private toggle.
12. **Mode field in chat store:** `mode: "chat" | "agent" | "research"` (default `"chat"`) +
    `setMode`.
13. **Unified send path:** one `use-chat.ts` hook merging the web app's `use-chat.ts` +
    `use-agent.ts` + `use-research-job.ts`. `send(content)` branches on `store.mode`:
    - `chat` → `streamChat` (plain-text SSE).
    - `agent` → `streamEvents("POST","/v1/agent/chat",...)` parsing `AgentEvent`s
      (`tool_call`/`tool_result`/`token`/`done`).
    - `research` → `researchApi.create()` then `streamEvents("GET","/v1/research/{id}/stream")`
      parsing `ResearchEvent`s (`progress`/`done`/`error`).
    All three use an `AbortController`; `isStreaming`/`streamError`/`pendingUserContent` shared.
14. **Inline rendering:** agent tool-step cards (adapt `ToolStepCard.tsx`) + research progress
    card (stage + progress bar + sources) render as ephemeral bubbles above the answer. Both
    are transient (not persisted to the conversation — the backend's agent/research endpoints
    don't write to `messages` today).

### Phase 3 — Image generation

15. **Image generation screen:** `mobile/app/(tabs)/(images)/index.tsx`, adapting
    `frontend/src/pages/images.tsx` (19.3KB):
    - Prompt + collapsible negative-prompt `TextInput`.
    - Aspect-ratio button grid fetched from `imageApi.aspectRatios()` (backend owns the list).
    - Collapsible controls: steps slider, cfg slider, seed input, batch stepper, rewrite
      `Switch`, template + workflow dropdowns.
    - Generate → `useImageGeneration` hook (port from web: polls `imageApi.status(promptId)`
      every 2s up to 90 times).
    - Results: image grid, tap to fullscreen `Modal`, long-press to save via `expo-media-library`.
    - History: `FlatList` from `image-store` (AsyncStorage), tap to re-open.
16. **Image URL fetching (S3 shipped):** image status URLs are now **relative**
    `/v1/images/file?...` and require the auth token. The SPA should use the returned
    `url` directly (same gateway origin, so the normal Authorization header applies) and
    remove any `/view` URL rewriting — the open Caddy `/view*` proxy is gone, so
    `getImageDisplayUrl()` must not rewrite ComfyUI hosts anymore.

### Phase 4 — Settings + config screens

17. **Settings menu** → Account (email + logout), Gateway (change URL), Presets, Templates,
    Workflows, Cookbook, Agent Tools.
18. **Presets/Templates/Workflows:** CRUD screens adapting the web `PresetForm`/`TemplateForm`/
    `WorkflowForm` to RN inputs. Workflows use a full-screen monospace `TextInput` for the
    ComfyUI JSON graph (no graph editor).
19. **Cookbook:** read-only — `hardwareApi.hardware()` + `hardwareApi.cookbook()`, GPU info +
    ranked model fit scores.
20. **Agent tools:** `agentApi.tools()` list + `Switch` per tool bound to `setPermission`.
    First-party allowed by default; MCP deny by default.

### Phase 5 — Polish

21. **Theme:** `mobile/src/theme.ts` with the color tokens from `frontend/src/index.css`
    (deep-purple canvas `#0D0B1E`, coral `#FF8A6A`, gold `#FFC85C`). One dark theme, `StyleSheet`.
22. **Native polish:** `SafeAreaView` (notch/home-indicator), `expo-haptics` (send/image
    complete/error), `KeyboardAvoidingView` (composer above keyboard), `ActivityIndicator`
    loading states, empty states, error banners (reuse `ApiError` classification), simple toast
    system.
23. **Build:** `npx expo run:android` (emulator/USB). Standalone APK via
    `eas build --platform android --profile preview` (sideloaded, no app store).

## Verification

- **Phase 1:** app launches → onboarding → enter gateway URL → `GET /health` → login →
  register → main tabs. Kill + relaunch → silent refresh → main tabs (no login).
- **Phase 2:** send a message → tokens stream in real-time. Toggle Agent → tool cards + answer
  inline. Toggle Research → progress card + synthesized answer + sources. Stop cancels
  mid-stream. Open a conversation → continues the thread.
- **Phase 3:** enter prompt → select ratio → generate → image appears → fullscreen → save to
  gallery. Rewrite toggle on → prompt rewritten. History list populates.
- **Phase 4:** preset/template/workflow CRUD persists. Cookbook shows GPU + fit scores. Tool
  permission toggle respected by the next agent run.
- **Phase 5:** safe areas on all screens. Haptics on send. `eas build` → APK → sideload on a
  phone → enter tailnet gateway URL → full app works over Tailscale.

## Critical files (web app → port from)
- `frontend/src/lib/types.ts` — complete backend contract; ports verbatim.
- `frontend/src/lib/api-client.ts:177-262,270-322` — SSE parsing logic to reimplement on
  `react-native-sse`.
- `frontend/src/lib/api-client.ts:102-167` — 401-refresh-retry + coalescing; ports to RN `fetch`.
- `frontend/src/hooks/use-chat.ts` + `use-agent.ts` + `use-research-job.ts` — three streaming
  hooks that merge into one mode-dispatching `use-chat.ts`.
- `frontend/src/lib/utils.ts:76-86` — `getImageDisplayUrl()` (ComfyUI host rewrite; **no
  longer needed** — see "Image URL fetching (S3 shipped)" in Phase 3).

## Assumptions
- **`react-native-sse` is the SSE transport** (supports POST + custom headers). Fallback:
  `@microsoft/fetch-event-source` + ReadableStream polyfill if it breaks on the target RN
  version. Test it first in Phase 1 with a simple chat send.
- **The web frontend is NOT deleted** — stays as the desktop/reference client.
- **Provider API is plain JSON CRUD — no SSE.** The provider list/create/update/delete/test
  endpoints use ordinary `apiClient.request()` calls; only chat/agent/research stream.
- **Agent + Research results are ephemeral** in the UI (not persisted to the conversation),
  matching the web app. If persistence is later wanted, that requires a backend change
  (write research answer as a `Message`) — out of scope here.
- **Image files are fetched through the authed `/v1/images/file?...` route (S3).**
  The backend returns relative URLs on job status; the app uses them as-is with the
  normal Authorization header. No `/view` proxying or host rewriting.
- **Gateway URL is a user-entered setting**, not a build-time env var (no rebuild to change
  URL). Fallback: `EXPO_PUBLIC_GATEWAY_URL` EAS env var if a baked-in URL is preferred.
- **Android-first; iOS later** (same codebase; iOS build needs Apple Developer credentials).
- **No automated tests** (the web app has none). Manual verification per the Verification
  section. If tests are later wanted: React Native Testing Library + Jest.
- **Gateway operator onboarding is handled by `setup.ps1`/`setup.sh`** — they generate
  `.env` and start the stack; the mobile app's first-launch onboarding remains a single
  gateway-URL entry.
