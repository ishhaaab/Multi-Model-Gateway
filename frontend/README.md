# llm-gateway — Frontend

React + Vite + TypeScript frontend for the llm-gateway backend. Dark, editorial UI
(deep-purple canvas, coral/gold accents, Instrument Serif headings) built with
Tailwind CSS v4, Zustand, and react-router.

## Stack

- **React + Vite + TypeScript**
- **Tailwind CSS v4** (`@tailwindcss/vite`, CSS-first theme in `src/index.css`)
- **Zustand** for state, **react-router-dom** for routing
- **react-markdown + remark-gfm + rehype-highlight** for chat message rendering
- **lucide-react** icons

## Setup

```bash
npm install
cp .env.example .env   # then edit if needed
npm run dev            # http://localhost:5173
```

The backend is expected at `http://localhost:2727` (the Docker-mapped port).

## Environment variables

| Var | Dev default | Notes |
|---|---|---|
| `VITE_API_URL` | `http://localhost:2727` | Backend base URL |
| `VITE_API_PREFIX` | `` (empty) | Use `/api` when behind the Caddy reverse proxy |
| `VITE_COMFYUI_HOST` | `http://localhost:8188` | Rewrites ComfyUI image URLs (which point at `host.docker.internal:8188`) |

For production behind Caddy, the built frontend is served on port `6969` and the
API is reached via `/api` — set `VITE_API_PREFIX=/api`.

## Scripts

- `npm run dev` — dev server
- `npm run build` — typecheck (`tsc -b`) + production build to `dist/`
- `npm run preview` — preview the production build

## Project structure

```
src/
  lib/         types, api-client (auth interceptor + SSE), endpoints, utils, config
  stores/      zustand: auth, chat, preset, template, ui (toasts)
  hooks/       use-chat (SSE streaming), use-image (ComfyUI polling)
  components/  ui/ primitives, layout/ shell + sidebar, chat/ message UI
  pages/       login, register, chat, images, presets, templates, settings, not-found
```

## Image generation — aspect ratios

The `aspect_ratio` value is forwarded **verbatim** to ComfyUI's `ResolutionSelector`
node, so the options must match the strings that node accepts. They live in a single
array in `src/lib/utils.ts`:

```ts
export const ASPECT_RATIOS = [
  "1:1 (Square)",
  "3:2 (Photo)",
  "4:3 (Standard)",
  "16:9 (Widescreen)",
  "21:9 (Ultrawide)",
  "2:3 (Portrait Photo)",
  "3:4 (Portrait Standard)",
  "9:16 (Portrait Widescreen)",
] as const;

// Backend default (backend/app/routers/images.py)
export const DEFAULT_ASPECT_RATIO: AspectRatio = "9:16 (Portrait Widescreen)";
```

**To add more ratios:** append the exact node string to `ASPECT_RATIOS`. The image-gen
button grid and the generate request both read from this array — nothing else to change.

## Backend behaviors the UI relies on

- Chat auto-routing only happens when `model: "auto"` is sent; the UI always sends it.
- Chat SSE frames tokens as `data: <content>\n\n`, ends with `data: [DONE]`, and emits
  errors **without** a `data:` prefix — the client parses both.
- `GET /v1/convo` and `GET /v1/convo/{id}` return bare arrays; presets/templates lists
  are wrapped in `{ data: [...] }`. Messages share an `index` per turn and are sorted
  client-side (user before assistant).
