import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { ArrowUp, Square, Lock } from "lucide-react";
import { useChatStore } from "@/stores/chat-store";
import { usePresetStore } from "@/stores/preset-store";
import type { Provider } from "@/lib/types";
import { cn, PROVIDER_DOT } from "@/lib/utils";
import { Dropdown } from "@/components/ui/Dropdown";
import type { DropdownOption } from "@/components/ui/Dropdown";

const PROVIDER_OPTIONS: DropdownOption[] = [
  { value: "auto", label: "Auto", dotColor: PROVIDER_DOT.auto },
  { value: "local", label: "Local", dotColor: PROVIDER_DOT.local },
  { value: "openrouter", label: "OpenRouter", dotColor: PROVIDER_DOT.openrouter },
];

const MAX_TEXTAREA_HEIGHT = 168; // ~6 lines

interface ChatInputProps {
  onSend: (content: string) => void;
  onCancel: () => void;
  isStreaming: boolean;
}

export function ChatInput({ onSend, onCancel, isStreaming }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const provider = useChatStore((s) => s.provider);
  const setProvider = useChatStore((s) => s.setProvider);
  const presetId = useChatStore((s) => s.presetId);
  const setPresetId = useChatStore((s) => s.setPresetId);
  const isPrivate = useChatStore((s) => s.isPrivate);
  const setPrivate = useChatStore((s) => s.setPrivate);
  const presets = usePresetStore((s) => s.presets);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [value]);

  const presetOptions: DropdownOption[] = [
    { value: "", label: "No preset", sublabel: "Use defaults" },
    ...presets.map((p) => ({
      value: p.id,
      label: p.name,
      sublabel: `temp ${p.temperature}`,
    })),
  ];

  const submit = () => {
    const content = value.trim();
    if (!content || isStreaming) return;
    onSend(content);
    setValue("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const canSend = value.trim().length > 0 && !isStreaming;

  return (
    <div className="border-t border-border bg-bg-secondary/70 px-4 py-3">
      <div className="mx-auto w-full max-w-3xl">
        {/* Toolbar */}
        <div className="mb-2 flex items-center gap-2">
          <Dropdown
            value={provider}
            options={PROVIDER_OPTIONS}
            onChange={(v) => setProvider(v as Provider)}
            size="sm"
            up
            className="w-[140px]"
          />
          <Dropdown
            value={presetId ?? ""}
            options={presetOptions}
            onChange={(v) => setPresetId(v || null)}
            size="sm"
            up
            className="w-[170px]"
          />
          <button
            type="button"
            onClick={() => setPrivate(!isPrivate)}
            title="Private mode — forces the request to the local provider only"
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-lg border transition-colors",
              isPrivate
                ? "border-accent-secondary/50 bg-accent-secondary/10 text-accent-secondary"
                : "border-border bg-bg-secondary text-text-muted hover:text-text-primary hover:bg-bg-tertiary"
            )}
            aria-pressed={isPrivate}
          >
            <Lock size={15} />
          </button>
        </div>

        {/* Input row */}
        <div className="flex items-end gap-2 rounded-xl border border-border bg-bg-secondary px-3 py-2 focus-within:ring-2 focus-within:ring-accent-primary/70">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={isStreaming}
            rows={1}
            placeholder={isStreaming ? "Generating…" : "Message…"}
            className="flex-1 resize-none bg-transparent py-1.5 text-[0.9375rem] text-text-primary placeholder:text-text-muted outline-none disabled:opacity-60"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={onCancel}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-bg-tertiary text-text-primary transition-colors hover:bg-bg-elevated"
              aria-label="Stop generating"
            >
              <Square size={15} className="fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={!canSend}
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-all duration-150",
                canSend
                  ? "bg-accent-primary text-white hover:brightness-110 active:scale-95"
                  : "bg-bg-tertiary text-text-muted"
              )}
              aria-label="Send message"
            >
              <ArrowUp size={17} />
            </button>
          )}
        </div>

        {isStreaming && (
          <div className="mt-2 flex items-center gap-2 px-1 text-[0.75rem] text-text-muted">
            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent-primary" />
            Generating…
          </div>
        )}
      </div>
    </div>
  );
}
