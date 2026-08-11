import type { ChatRequest } from "./types";
import { useAuthStore } from "@/stores/auth-store";

export class ApiError extends Error {
  statusCode: number;
  detail: string;

  constructor(statusCode: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.detail = detail;
  }

  get isAuthError() {
    return this.statusCode === 401;
  }
  get isRateLimit() {
    return this.statusCode === 429;
  }
  get isNotFound() {
    return this.statusCode === 404;
  }
  get isNetworkError() {
    return this.statusCode === 0;
  }
}

const NETWORK_MESSAGE =
  "Cannot connect to server. Check if the backend is running.";

interface ApiClientConfig {
  baseUrl: string;
  apiPrefix: string;
  getAccessToken: () => string | null;
  getRefreshToken: () => string | null;
  onRefresh: (accessToken: string, refreshToken: string) => void;
  onAuthFailure: () => void;
}

class ApiClient {
  private baseUrl: string;
  private apiPrefix: string;
  private getAccessToken: () => string | null;
  private getRefreshToken: () => string | null;
  private onRefresh: (accessToken: string, refreshToken: string) => void;
  private onAuthFailure: () => void;

  // Coalesce concurrent refreshes into a single in-flight request.
  private refreshInFlight: Promise<boolean> | null = null;

  constructor(config: ApiClientConfig) {
    this.baseUrl = config.baseUrl;
    this.apiPrefix = config.apiPrefix;
    this.getAccessToken = config.getAccessToken;
    this.getRefreshToken = config.getRefreshToken;
    this.onRefresh = config.onRefresh;
    this.onAuthFailure = config.onAuthFailure;
  }

  private fullUrl(path: string): string {
    return `${this.baseUrl}${this.apiPrefix}${path}`;
  }

  private buildHeaders(body: unknown, stream: boolean): Record<string, string> {
    const headers: Record<string, string> = {};
    // FormData sets its own multipart Content-Type (with a boundary) — let the
    // browser fill it in, or the server can't parse the body.
    if (body !== undefined && body !== null && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    if (stream) {
      headers["Accept"] = "text/event-stream";
    }
    const token = this.getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }

  private async rawFetch(
    url: string,
    method: string,
    headers: Record<string, string>,
    body: unknown,
    signal?: AbortSignal
  ): Promise<Response> {
    try {
      return await fetch(url, {
        method,
        headers,
        body:
          body instanceof FormData
            ? body
            : body !== undefined && body !== null
              ? JSON.stringify(body)
              : undefined,
        signal,
      });
    } catch (err) {
      if ((err as Error)?.name === "AbortError") throw err;
      // fetch rejects (TypeError) only on network-level failures
      throw new ApiError(0, NETWORK_MESSAGE);
    }
  }

  /** Core JSON request with one transparent token-refresh + retry on 401. */
  async request<T>(
    method: string,
    path: string,
    body?: unknown,
    options?: { stream?: boolean; signal?: AbortSignal }
  ): Promise<T> {
    const url = this.fullUrl(path);
    const stream = options?.stream ?? false;
    let headers = this.buildHeaders(body, stream);

    let response = await this.rawFetch(url, method, headers, body, options?.signal);

    if (response.status === 401 && this.getRefreshToken()) {
      const refreshed = await this.tryRefreshToken();
      if (refreshed) {
        headers = this.buildHeaders(body, stream);
        response = await this.rawFetch(url, method, headers, body, options?.signal);
      } else {
        this.onAuthFailure();
        throw new ApiError(401, "Session expired. Please log in again.");
      }
    }

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: "Request failed" }));
      throw new ApiError(response.status, error.detail || "Request failed");
    }

    if (stream) {
      return response as unknown as T;
    }

    // 204 / empty body guard
    const text = await response.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  /**
   * Fetch a binary resource (e.g. an image) with the Authorization header.
   *
   * `<img src>` can't send headers, so the backend's relative `/v1/images/file?`
   * URLs are fetched here and rendered via blob URLs. Mirrors request()'s
   * 401-refresh-retry so expired sessions recover transparently, but treats
   * every 401 as an auth failure — with no refresh token there's nothing to
   * recover from, so we sign out instead of falling through as a plain error.
   */
  async fetchBlob(
    path: string,
    signal?: AbortSignal
  ): Promise<{ blob: Blob; contentType: string }> {
    const url = this.fullUrl(path);
    let headers = this.buildHeaders(undefined, false);

    let response = await this.rawFetch(url, "GET", headers, undefined, signal);

    if (response.status === 401) {
      if (this.getRefreshToken()) {
        const refreshed = await this.tryRefreshToken();
        if (refreshed) {
          headers = this.buildHeaders(undefined, false);
          response = await this.rawFetch(url, "GET", headers, undefined, signal);
          // A retried request that STILL 401s means the refreshed session is
          // not accepted — treat it as session expiry rather than a plain error.
          if (response.status === 401) {
            this.onAuthFailure();
            throw new ApiError(401, "Session expired. Please log in again.");
          }
        } else {
          this.onAuthFailure();
          throw new ApiError(401, "Session expired. Please log in again.");
        }
      } else {
        this.onAuthFailure();
        throw new ApiError(401, "Session expired. Please log in again.");
      }
    }

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: "Request failed" }));
      throw new ApiError(response.status, error.detail || "Request failed");
    }

    return {
      blob: await response.blob(),
      contentType:
        response.headers.get("content-type") || "application/octet-stream",
    };
  }

  private tryRefreshToken(): Promise<boolean> {
    if (this.refreshInFlight) return this.refreshInFlight;

    this.refreshInFlight = (async () => {
      const refreshToken = this.getRefreshToken();
      if (!refreshToken) return false;
      try {
        const response = await fetch(this.fullUrl("/auth/refresh"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) return false;
        const data = await response.json();
        // Backend rotates the refresh token on every use — persist the new one
        // or the next refresh will fail with the now-invalidated old token.
        this.onRefresh(data.access_token, data.refresh_token);
        return true;
      } catch {
        return false;
      } finally {
        this.refreshInFlight = null;
      }
    })();

    return this.refreshInFlight;
  }

  /**
   * SSE streaming for chat.
   *
   * The backend frames each chunk as `data: <content>\n\n`, terminates with
   * `data: [DONE]\n\n`, and emits errors as `data: [ERROR] <msg>\n\n`. We parse
   * on the `\n\n` event boundary so multi-line tokens survive, and still tolerate
   * the legacy `ERROR:` / `Internal server error` shapes.
   */
  async streamChat(
    body: ChatRequest,
    onToken: (token: string) => void,
    onDone: () => void,
    onError: (error: string) => void,
    signal?: AbortSignal
  ): Promise<void> {
    let response: Response;
    try {
      response = await this.request<Response>("POST", "/v1/chat/completions", body, {
        stream: true,
        signal,
      });
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      if (err instanceof ApiError) {
        if (err.isRateLimit) return onError("Rate limit exceeded. Try again later.");
        return onError(err.detail);
      }
      return onError((err as Error)?.message || NETWORK_MESSAGE);
    }

    const reader = response.body?.getReader();
    if (!reader) return onError("Streaming not supported by this browser.");

    const decoder = new TextDecoder();
    let buffer = "";

    const handleEvent = (rawEvent: string): boolean => {
      const event = rawEvent.replace(/\r/g, "");
      if (event.length === 0) return false;

      if (event.startsWith("data: ")) {
        const payload = event.slice(6);
        if (payload === "[DONE]") {
          onDone();
          return true;
        }
        if (payload.startsWith("[ERROR]")) {
          onError(payload.slice(7).trim() || "Something went wrong.");
          return true;
        }
        if (payload.startsWith("ERROR: ")) {
          onError(payload.slice(7));
          return true;
        }
        onToken(payload);
        return false;
      }

      // Un-prefixed error frames from the backend
      if (event.startsWith("ERROR: ")) {
        onError(event.slice(7));
        return true;
      }
      if (event.trim() === "Internal server error") {
        onError("Internal server error");
        return true;
      }
      return false;
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const ev of events) {
          if (handleEvent(ev)) return;
        }
      }
      // Flush any trailing event the stream ended without a blank line on
      if (buffer.length > 0) {
        if (handleEvent(buffer)) return;
      }
      onDone();
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        onError((err as Error)?.message || NETWORK_MESSAGE);
      }
    }
  }

  /**
   * Generic SSE reader for endpoints that frame each `data:` line as a JSON
   * object (agent steps, research progress). Yields the parsed objects. Unlike
   * streamChat (plain `data: <token>`), this does NOT touch the chat parser, so
   * existing chat streaming is unaffected. Auth/refresh is handled by request().
   */
  async *streamEvents<T = unknown>(
    method: string,
    path: string,
    body?: unknown,
    signal?: AbortSignal
  ): AsyncGenerator<T> {
    const response = await this.request<Response>(method, path, body, {
      stream: true,
      signal,
    });
    const reader = response.body?.getReader();
    if (!reader) throw new ApiError(0, "Streaming not supported by this browser.");

    const decoder = new TextDecoder();
    let buffer = "";

    const parse = (raw: string): T | undefined => {
      const event = raw.replace(/\r/g, "").trim();
      if (!event.startsWith("data:")) return undefined;
      const payload = event.slice(5).trim();
      if (!payload || payload === "[DONE]") return undefined;
      try {
        return JSON.parse(payload) as T;
      } catch {
        return undefined; // tolerate keep-alives / non-JSON frames
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const ev of events) {
          const obj = parse(ev);
          if (obj !== undefined) yield obj;
        }
      }
      const tail = parse(buffer);
      if (tail !== undefined) yield tail;
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      throw err;
    } finally {
      try {
        reader.releaseLock();
      } catch {
        /* already released */
      }
    }
  }
}

export const apiClient = new ApiClient({
  baseUrl: import.meta.env.VITE_API_URL || "http://localhost:2727",
  apiPrefix: import.meta.env.VITE_API_PREFIX || "",
  getAccessToken: () => useAuthStore.getState().accessToken,
  getRefreshToken: () => useAuthStore.getState().refreshToken,
  onRefresh: (access, refresh) => useAuthStore.getState().setTokens(access, refresh),
  onAuthFailure: () => useAuthStore.getState().forceLogout(),
});
