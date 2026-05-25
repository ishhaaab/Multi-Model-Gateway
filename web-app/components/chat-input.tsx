'use client'

import { useRef, useEffect, KeyboardEvent } from 'react'
import { ArrowUp, Square, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// ─── Provider badge ───────────────────────────────────────────────────────────

const PROVIDER_LABELS: Record<string, string> = {
  auto: 'auto',
  local: 'local',
  openrouter: 'OR',
}

const PROVIDER_COLORS: Record<string, string> = {
  auto: 'bg-muted text-muted-foreground',
  local: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  openrouter: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface ChatInputProps {
  onSend: (content: string) => void
  onAbort: () => void
  isStreaming: boolean
  selectedModel: string
  selectedProvider: string
  onModelClick: () => void
  className?: string
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ChatInput({
  onSend,
  onAbort,
  isStreaming,
  selectedModel,
  selectedProvider,
  onModelClick,
  className,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea (1–6 lines)
  function resize() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const lineHeight = 24
    const minHeight = lineHeight
    const maxHeight = lineHeight * 6
    el.style.height = `${Math.min(Math.max(el.scrollHeight, minHeight), maxHeight)}px`
  }

  useEffect(() => {
    resize()
  }, [])

  function handleInput() {
    resize()
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function submit() {
    const el = textareaRef.current
    if (!el) return
    const content = el.value.trim()
    if (!content || isStreaming) return
    onSend(content)
    el.value = ''
    resize()
    el.focus()
  }

  const providerLabel = PROVIDER_LABELS[selectedProvider] ?? selectedProvider
  const providerColor = PROVIDER_COLORS[selectedProvider] ?? PROVIDER_COLORS.auto

  // Shorten model name for display
  const shortModel = selectedModel
    ? selectedModel.split('/').pop() ?? selectedModel
    : 'Select model'

  return (
    <div className={cn('border-t border-border bg-background px-4 py-3', className)}>
      {/* Textarea container */}
      <div className="relative flex items-end gap-2 rounded-xl border border-input bg-background px-3 py-2 shadow-sm focus-within:ring-2 focus-within:ring-ring/40 transition-shadow">
        <textarea
          ref={textareaRef}
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
          rows={1}
          aria-label="Message input"
          className={cn(
            'flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none leading-6',
            'max-h-[144px] overflow-y-auto',
          )}
        />

        {/* Stop / Send button */}
        {isStreaming ? (
          <button
            onClick={onAbort}
            aria-label="Stop generation"
            className="shrink-0 flex size-8 items-center justify-center rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
          >
            <Square className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            onClick={submit}
            aria-label="Send message"
            disabled={isStreaming}
            className={cn(
              'shrink-0 flex size-8 items-center justify-center rounded-lg transition-colors',
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'disabled:opacity-40 disabled:cursor-not-allowed',
            )}
          >
            <ArrowUp className="size-4" />
          </button>
        )}
      </div>

      {/* Bottom toolbar */}
      <div className="mt-2 flex items-center gap-2">
        {/* Model selector pill */}
        <button
          onClick={onModelClick}
          aria-label="Select model"
          className="flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <span className="truncate max-w-[180px] font-mono">{shortModel}</span>
          <ChevronDown className="size-3 shrink-0" />
        </button>

        {/* Provider badge */}
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
            providerColor,
          )}
        >
          {providerLabel}
        </span>
      </div>
    </div>
  )
}
