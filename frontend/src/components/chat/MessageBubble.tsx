import { useState } from "react";
import { Check, Copy } from "lucide-react";
import type { Message } from "@/lib/types";
import { formatRelativeTime, formatCompact, getProviderInfo } from "@/lib/utils";
import { Markdown } from "./Markdown";

interface MessageBubbleProps {
  role: "user" | "assistant" | "system";
  content: string;
  message?: Message;
  /** Show the pulsing streaming cursor at the end of assistant content. */
  streaming?: boolean;
}

function CopyButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(content);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard may be unavailable over http */
        }
      }}
      className="flex h-6 w-6 items-center justify-center rounded-md text-text-muted opacity-0 transition-opacity hover:bg-bg-elevated hover:text-text-primary group-hover:opacity-100"
      aria-label="Copy message"
    >
      {copied ? <Check size={13} className="text-success" /> : <Copy size={13} />}
    </button>
  );
}

export function MessageBubble({ role, content, message, streaming }: MessageBubbleProps) {
  if (role === "user") {
    return (
      <div className="group flex flex-col items-end gap-1 animate-slide-up">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-[#3A2D5E] px-4 py-2.5 text-text-primary">
          <p className="whitespace-pre-wrap break-words text-[0.9375rem] leading-relaxed">
            {content}
          </p>
        </div>
        {message && (
          <span className="px-1 text-[0.7rem] text-text-muted">
            {formatRelativeTime(message.created_at)}
          </span>
        )}
      </div>
    );
  }

  // assistant / system
  const provider = message?.model_used ? getProviderInfo(message.model_used) : null;

  return (
    <div className="group flex flex-col items-start gap-1 animate-slide-up">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-bg-tertiary px-4 py-3 text-text-primary">
        {content ? (
          <Markdown content={content} />
        ) : streaming ? (
          <span className="inline-flex gap-1 py-1">
            <span className="h-2 w-2 animate-pulse-dot rounded-full bg-accent-primary" />
            <span
              className="h-2 w-2 animate-pulse-dot rounded-full bg-accent-primary"
              style={{ animationDelay: "0.2s" }}
            />
            <span
              className="h-2 w-2 animate-pulse-dot rounded-full bg-accent-primary"
              style={{ animationDelay: "0.4s" }}
            />
          </span>
        ) : null}
        {streaming && content && (
          <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse-dot rounded-full bg-accent-primary align-middle" />
        )}
      </div>

      <div className="flex items-center gap-2 px-1">
        {provider && (
          <span className="flex items-center gap-1.5 text-[0.7rem] text-text-muted">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: provider.color }}
            />
            <span>{provider.provider}</span>
            <span className="font-mono">· {message?.model_used}</span>
          </span>
        )}
        {message?.tokens_used ? (
          <span className="text-[0.7rem] text-text-muted">
            {formatCompact(message.tokens_used)} tok
          </span>
        ) : null}
        {content && !streaming && <CopyButton content={content} />}
      </div>
    </div>
  );
}
