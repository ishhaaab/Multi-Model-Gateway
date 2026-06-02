import { useEffect, useRef, useState } from "react";
import { useChatStore } from "@/stores/chat-store";
import { usePresetStore } from "@/stores/preset-store";
import { toast } from "@/stores/ui-store";
import { PROVIDER_DOT, formatCompact } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";

const PROVIDER_LABEL: Record<string, string> = {
  auto: "Auto",
  local: "Local",
  openrouter: "OpenRouter",
};

export function ChatHeader() {
  const activeId = useChatStore((s) => s.activeConversationId);
  const conversations = useChatStore((s) => s.conversations);
  const provider = useChatStore((s) => s.provider);
  const presetId = useChatStore((s) => s.presetId);
  const isPrivate = useChatStore((s) => s.isPrivate);
  const renameConversation = useChatStore((s) => s.renameConversation);
  const presets = usePresetStore((s) => s.presets);

  const convo = conversations.find((c) => c.id === activeId);
  const preset = presets.find((p) => p.id === presetId);

  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = async () => {
    setEditing(false);
    const title = value.trim();
    if (!convo || !title || title === convo.title) return;
    try {
      await renameConversation(convo.id, title);
    } catch {
      toast.error("Could not rename conversation.");
    }
  };

  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-bg-secondary/60 px-5 py-3">
      <div className="flex min-w-0 flex-col gap-0.5">
        {editing && convo ? (
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") setEditing(false);
            }}
            className="w-full max-w-md rounded-md bg-bg-primary px-2 py-1 text-base text-text-primary outline-none ring-1 ring-accent-primary"
          />
        ) : (
          <button
            onClick={() => {
              if (!convo) return;
              setValue(convo.title);
              setEditing(true);
            }}
            disabled={!convo}
            className="max-w-md truncate text-left text-base text-text-primary hover:text-accent-primary transition-colors disabled:hover:text-text-primary"
            title={convo ? "Click to rename" : undefined}
          >
            {convo ? convo.title || "Untitled" : "New chat"}
          </button>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <Badge dotColor={PROVIDER_DOT[provider]}>{PROVIDER_LABEL[provider]}</Badge>
        {isPrivate && <Badge dotColor="#FFC85C">Private</Badge>}
        {preset && <Badge>{preset.name}</Badge>}
        {convo && convo.token_count > 0 && (
          <Badge>{formatCompact(convo.token_count)} tokens</Badge>
        )}
      </div>
    </header>
  );
}
