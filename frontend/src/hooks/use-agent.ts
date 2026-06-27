import { useCallback, useRef, useState } from "react";
import { useChatStore } from "@/stores/chat-store";
import { agentApi } from "@/lib/api-endpoints";
import { ApiError } from "@/lib/api-client";
import type { AgentEvent, ChatRequest } from "@/lib/types";

export interface AgentStep {
  id: string;
  name: string;
  arguments?: string; // present from tool_call
  content?: string; // present once tool_result arrives
}

export interface AgentTurn {
  user: string;
  steps: AgentStep[];
  answer: string;
}

/**
 * Agent streaming lifecycle. Mirrors use-chat (send/cancel) but consumes the
 * structured JSON SSE (tool_call / tool_result / token / done) into a list of
 * turns, each holding its tool steps and the final answer.
 */
export function useAgent() {
  const [turns, setTurns] = useState<AgentTurn[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const convoIdRef = useRef<string | null>(null);

  const send = useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text || isStreaming) return;
      setError(null);
      setTurns((t) => [...t, { user: text, steps: [], answer: "" }]);
      setIsStreaming(true);

      // Reuse the chat composer selections (same ChatRequest body shape).
      const store = useChatStore.getState();
      const body: ChatRequest = {
        conversation_id: convoIdRef.current,
        preset_id: store.presetId,
        messages: [{ role: "user", content: text }],
        model: store.model,
        stream: true,
        provider: store.provider,
        private: store.isPrivate,
      };

      const controller = new AbortController();
      abortRef.current = controller;

      // Patch only the in-flight (last) turn.
      const patchLast = (fn: (turn: AgentTurn) => AgentTurn) =>
        setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? fn(turn) : turn)));

      try {
        for await (const event of agentApi.chatStream(body, controller.signal)) {
          const ev = event as AgentEvent;
          if (ev.type === "tool_call") {
            patchLast((turn) => ({
              ...turn,
              steps: [...turn.steps, { id: ev.id, name: ev.name, arguments: ev.arguments }],
            }));
          } else if (ev.type === "tool_result") {
            patchLast((turn) => ({
              ...turn,
              steps: turn.steps.some((s) => s.id === ev.id)
                ? turn.steps.map((s) => (s.id === ev.id ? { ...s, content: ev.content } : s))
                : [...turn.steps, { id: ev.id, name: ev.name, content: ev.content }],
            }));
          } else if (ev.type === "token") {
            patchLast((turn) => ({ ...turn, answer: turn.answer + ev.content }));
          } else if (ev.type === "error") {
            setError(ev.message || "The agent ran into an error.");
          } else if (ev.type === "done") {
            convoIdRef.current = ev.conversation_id ?? convoIdRef.current;
          }
        }
      } catch (err) {
        if ((err as Error)?.name !== "AbortError") {
          setError(err instanceof ApiError ? err.detail : "Agent request failed.");
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [isStreaming]
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    convoIdRef.current = null;
    setTurns([]);
    setError(null);
    setIsStreaming(false);
  }, []);

  return { turns, isStreaming, error, send, cancel, reset };
}
