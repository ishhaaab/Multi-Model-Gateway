'use client'

import { useEffect, useRef, useState, KeyboardEvent } from 'react'
import { ArrowUp, Square, ChevronDown, Check, Loader2 } from 'lucide-react'
import { modelsApi, type LocalModel, type OpenRouterModel } from '@/lib/api-models'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
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
  onSelect: (model: string, provider: string) => void
  className?: string
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ChatInput({
  onSend,
  onAbort,
  isStreaming,
  selectedModel,
  selectedProvider,
  onSelect,
  className,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [localModels, setLocalModels] = useState<LocalModel[]>([])
  const [orModels, setOrModels] = useState<OpenRouterModel[]>([])
  const [localLoading, setLocalLoading] = useState(false)
  const [orLoading, setOrLoading] = useState(false)
  const [mainMenuOpen, setMainMenuOpen] = useState(false)
  const [localSubOpen, setLocalSubOpen] = useState(false)
  const [orSubOpen, setOrSubOpen] = useState(false)

  useEffect(() => {
    setLocalLoading(true)
    modelsApi.getLocalModels()
      .then(({ data }) => setLocalModels(data))
      .catch(() => setLocalModels([]))
      .finally(() => setLocalLoading(false))

    setOrLoading(true)
    modelsApi.getOpenRouterModels()
      .then(({ data }) => setOrModels(data))
      .catch(() => setOrModels([]))
      .finally(() => setOrLoading(false))
  }, [])

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
        {/* Model selector dropdown */}
        <DropdownMenu open={mainMenuOpen} onOpenChange={setMainMenuOpen}>
          <DropdownMenuTrigger asChild>
            <button
              aria-label="Select model"
              className="flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <span className="truncate max-w-[180px] font-mono">{shortModel}</span>
              <ChevronDown className="size-3 shrink-0" />
            </button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="start" className="min-w-[180px]">
            <DropdownMenuItem onClick={() => { setMainMenuOpen(false); onSelect('auto', 'auto'); }}>
              <span className="flex items-center gap-2">
                Auto route
                {selectedProvider === 'auto' && <Check className="size-3.5" />}
              </span>
            </DropdownMenuItem>

            <DropdownMenuSeparator />

            <DropdownMenuSub open={localSubOpen} onOpenChange={setLocalSubOpen}>
              <DropdownMenuSubTrigger className="flex items-center gap-0 p-0">
                <span
                  onClick={(e) => { e.stopPropagation(); setLocalSubOpen(false); setMainMenuOpen(false); onSelect('auto', 'local'); }}
                  className="flex-1 flex items-center gap-2 px-2 py-1.5 hover:bg-accent/50 rounded-sm cursor-pointer"
                >
                  Local
                  {selectedProvider === 'local' && <Check className="size-3.5" />}
                </span>
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="min-w-[280px] max-h-64 overflow-y-auto">
                {localLoading ? (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="size-4 animate-spin text-muted-foreground" />
                  </div>
                ) : localModels.length === 0 ? (
                  <p className="px-2 py-3 text-xs text-muted-foreground text-center">
                    No local models found. Is LM Studio running?
                  </p>
                ) : (
                  localModels.map((m) => (
                    <DropdownMenuItem
                      key={m.id}
                      onClick={() => { setMainMenuOpen(false); onSelect(m.id, 'local'); }}
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        {selectedModel === m.id && selectedProvider === 'local' && (
                          <Check className="size-3.5 shrink-0" />
                        )}
                        <span className="font-mono text-xs truncate">{m.id}</span>
                      </span>
                    </DropdownMenuItem>
                  ))
                )}
              </DropdownMenuSubContent>
            </DropdownMenuSub>

            <DropdownMenuSub open={orSubOpen} onOpenChange={setOrSubOpen}>
              <DropdownMenuSubTrigger className="flex items-center gap-0 p-0">
                <span
                  onClick={(e) => { e.stopPropagation(); setOrSubOpen(false); setMainMenuOpen(false); onSelect('auto', 'openrouter'); }}
                  className="flex-1 flex items-center gap-2 px-2 py-1.5 hover:bg-accent/50 rounded-sm cursor-pointer"
                >
                  OpenRouter
                  {selectedProvider === 'openrouter' && <Check className="size-3.5" />}
                </span>
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="min-w-[280px] max-h-64 overflow-y-auto">
                {orLoading ? (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="size-4 animate-spin text-muted-foreground" />
                  </div>
                ) : orModels.length === 0 ? (
                  <p className="px-2 py-3 text-xs text-muted-foreground text-center">
                    No OpenRouter models available.
                  </p>
                ) : (
                  orModels.map((m) => (
                    <DropdownMenuItem
                      key={m.id}
                      onClick={() => { setMainMenuOpen(false); onSelect(m.id, 'openrouter'); }}
                    >
                      <span className="flex items-start gap-2 min-w-0">
                        {selectedModel === m.id && selectedProvider === 'openrouter' && (
                          <Check className="size-3.5 shrink-0 mt-0.5" />
                        )}
                        <span className="flex flex-col min-w-0">
                          <span className="text-sm truncate">{m.name}</span>
                          <span className="font-mono text-[10px] text-muted-foreground truncate">{m.id}</span>
                        </span>
                      </span>
                    </DropdownMenuItem>
                  ))
                )}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          </DropdownMenuContent>
        </DropdownMenu>

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
