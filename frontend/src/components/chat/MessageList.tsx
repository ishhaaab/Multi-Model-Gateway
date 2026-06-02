import { useEffect, useRef } from "react";
import { Sparkles, AlertTriangle, RotateCw } from "lucide-react";
import type { Message } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";
import { Skeleton } from "@/components/ui/Skeleton";

interface MessageListProps {
  messages: Message[];
  loading: boolean;
  pendingUserContent: string | null;
  streamedContent: string;
  isStreaming: boolean;
  streamError: string | null;
  onRetry: () => void;
}

export function MessageList({
  messages,
  loading,
  pendingUserContent,
  streamedContent,
  isStreaming,
  streamError,
  onRetry,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamedContent, pendingUserContent, isStreaming]);

  if (loading && messages.length === 0) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
        <Skeleton className="ml-auto h-14 w-1/2" />
        <Skeleton className="h-24 w-3/4" />
        <Skeleton className="ml-auto h-14 w-2/5" />
      </div>
    );
  }

  const isEmpty =
    messages.length === 0 && !pendingUserContent && !isStreaming;

  if (isEmpty) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center animate-fade-in">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-tertiary">
          <Sparkles size={26} className="text-accent-primary" />
        </span>
        <h2 className="text-2xl text-text-primary">Welcome to llm-gateway</h2>
        <p className="max-w-md text-sm text-text-secondary">
          Start by selecting a preset and provider, then type your message below.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            role={m.role}
            content={m.content}
            message={m}
          />
        ))}

        {/* Optimistic in-flight turn */}
        {pendingUserContent && (
          <MessageBubble role="user" content={pendingUserContent} />
        )}
        {isStreaming && (
          <MessageBubble role="assistant" content={streamedContent} streaming />
        )}

        {streamError && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 animate-fade-in">
            <span className="flex items-center gap-2 text-sm text-danger">
              <AlertTriangle size={16} />
              {streamError}
            </span>
            <button
              onClick={onRetry}
              className="flex items-center gap-1.5 rounded-md border border-danger/40 px-2.5 py-1 text-[0.8125rem] text-danger hover:bg-danger/10"
            >
              <RotateCw size={13} /> Retry
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
