'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertCircle, MessageSquarePlus, RefreshCw, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { useStreamChat } from '@/hooks/use-stream-chat'
import { ChatMessage } from '@/components/chat-message'
import { ChatInput } from '@/components/chat-input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

// ─── Suggestions for empty state ──────────────────────────────────────────────

const SUGGESTIONS = [
  'Explain quantum entanglement simply',
  'Write a Python function to parse JSON',
  'What are the best practices for REST API design?',
  'Summarize the history of the internet',
]

// ─── Loading skeleton for message history ────────────────────────────────────

function MessagesSkeleton() {
  return (
    <div className="flex flex-col gap-4 px-4 py-4">
      {[...Array(4)].map((_, i) => (
        <div key={i} className={cn('flex gap-3', i % 2 === 0 ? 'flex-row-reverse' : 'flex-row')}>
          <Skeleton className={cn('h-16 rounded-2xl', i % 2 === 0 ? 'w-48' : 'w-64')} />
        </div>
      ))}
    </div>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-12">
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-muted">
          <MessageSquarePlus className="size-6 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-foreground">Start a conversation</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Ask anything — I&apos;ll route your request to the best model.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap justify-center gap-2 max-w-md">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onSuggestion(s)}
            className="rounded-full border border-border bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── Error banner ─────────────────────────────────────────────────────────────

function ErrorBanner({ error, onRetry, onDismiss }: { error: string; onRetry: () => void; onDismiss: () => void }) {
  return (
    <div className="mx-4 mb-2 flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3">
      <AlertCircle className="size-4 shrink-0 text-destructive mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-destructive font-medium">Generation failed</p>
        <p className="text-xs text-muted-foreground mt-0.5 break-words">{error}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Button size="sm" variant="ghost" onClick={onRetry} className="h-7 gap-1 text-xs">
          <RefreshCw className="size-3" />
          Retry
        </Button>
        <Button size="sm" variant="ghost" onClick={onDismiss} className="h-7 text-xs">
          Dismiss
        </Button>
      </div>
    </div>
  )
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface ChatViewProps {
  conversationId: string | null
  onNewConversation?: (id: string) => void
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ChatView({ conversationId, onNewConversation }: ChatViewProps) {
  const router = useRouter()

  const [selectedModel, setSelectedModel] = useState('auto')
  const [selectedProvider, setSelectedProvider] = useState('auto')
  const [historyLoading, setHistoryLoading] = useState(!!conversationId)
  const [lastSent, setLastSent] = useState<{ content: string } | null>(null)

  const { messages, isStreaming, error, retryStatus, sendMessage, abort, clearError, setMessages } =
    useStreamChat(conversationId ?? undefined)

  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const userScrolledUp = useRef(false)
  const prevScrollTop = useRef(0)

  // Mark history as loaded once messages settle
  useEffect(() => {
    if (!conversationId) {
      setHistoryLoading(false)
      return
    }
    // useStreamChat loads messages internally; once it's done the messages array
    // will either have items or be empty. We give it a short window then clear.
    const timer = setTimeout(() => setHistoryLoading(false), 600)
    return () => clearTimeout(timer)
  }, [conversationId])

  // Auto-scroll to bottom unless user has scrolled up
  const scrollToBottom = useCallback((smooth = true) => {
    bottomRef.current?.scrollIntoView({ behavior: smooth ? 'smooth' : 'instant' })
  }, [])

  useEffect(() => {
    if (!userScrolledUp.current) {
      scrollToBottom(!historyLoading)
    }
  }, [messages, historyLoading, scrollToBottom])

  // Track user scroll direction
  function handleScroll(e: React.UIEvent<HTMLDivElement>) {
    const el = e.currentTarget
    const isScrollingUp = el.scrollTop < prevScrollTop.current
    prevScrollTop.current = el.scrollTop
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (isScrollingUp) {
      userScrolledUp.current = true
    }
    if (atBottom) {
      userScrolledUp.current = false
    }
  }

  async function handleSend(content: string) {
    setLastSent({ content })
    userScrolledUp.current = false

    const completed = await sendMessage(content, {
      model: selectedModel,
      provider: selectedProvider,
      conversationId,
    })

    // For new conversations: the backend auto-creates a convo and returns an id.
    // In real usage the streamChat response headers/body would contain the new id.
    // We trigger the parent callback so the sidebar refreshes and we navigate.
    // Only navigate when the stream completed successfully (not aborted/errored).
    if (completed && !conversationId && onNewConversation) {
      // We can't know the id from SSE alone without a custom header;
      // notify parent to refresh and let it pick the latest conversation.
      onNewConversation('')
    }
  }

  function handleSuggestion(text: string) {
    handleSend(text)
  }

  function handleRetry() {
    if (!lastSent) return
    clearError()
    // Remove the failed empty assistant message if present and retry
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      if (last?.role === 'assistant' && last.content === '') return prev.slice(0, -1)
      return prev
    })
    handleSend(lastSent.content)
  }

  const showEmpty = !historyLoading && messages.length === 0 && !isStreaming

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Messages area */}
      <div
        className="flex-1 min-h-0 overflow-y-auto"
        onScroll={handleScroll}
        ref={scrollAreaRef}
      >
        {historyLoading ? (
          <MessagesSkeleton />
        ) : showEmpty ? (
          <EmptyState onSuggestion={handleSuggestion} />
        ) : (
          <div className="flex flex-col py-4 pb-2">
            {messages.map((msg, i) => {
              const isLast = i === messages.length - 1
              return (
                <ChatMessage
                  key={i}
                  message={msg}
                  isStreaming={isLast && isStreaming && msg.role === 'assistant'}
                />
              )
            })}
            <div ref={bottomRef} className="h-1" />
          </div>
        )}
      </div>

      {/* Retry banner */}
      {retryStatus && (
        <div className="mx-4 mb-2 flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5">
          <Loader2 className="size-4 shrink-0 text-amber-500 animate-spin" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-amber-600 dark:text-amber-400">
              Rate limited — retrying {retryStatus.attempt}/{retryStatus.total}...
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Waiting for the provider to recover.
            </p>
          </div>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <ErrorBanner
          error={error}
          onRetry={handleRetry}
          onDismiss={clearError}
        />
      )}

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onAbort={abort}
        isStreaming={isStreaming}
        selectedModel={selectedModel}
        selectedProvider={selectedProvider}
        onSelect={(model, provider) => {
          setSelectedModel(model)
          setSelectedProvider(provider)
        }}
      />
    </div>
  )
}
