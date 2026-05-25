'use client'

import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MarkdownRenderer } from '@/components/markdown-renderer'
import type { Message } from '@/lib/api-conversations'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTime(dateStr?: string): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// ─── Typing cursor ────────────────────────────────────────────────────────────

function TypingCursor() {
  return (
    <span className="inline-flex items-end ml-0.5 h-4">
      <span className="inline-block w-0.5 h-3.5 bg-current animate-pulse rounded-sm" />
    </span>
  )
}

// ─── Typing indicator (empty assistant message while streaming) ───────────────

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-0.5" aria-label="Assistant is typing">
      <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
      <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
      <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
    </div>
  )
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface ChatMessageProps {
  message: Message
  isStreaming?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'
  const isEmpty = !message.content

  function copyContent() {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div
      className={cn(
        'group/msg flex gap-3 px-4 py-2',
        isUser ? 'flex-row-reverse' : 'flex-row',
      )}
    >
      {/* Bubble */}
      <div
        className={cn(
          'relative max-w-[75%] min-w-0 rounded-2xl px-4 py-2.5 text-sm',
          isUser
            ? 'bg-primary text-primary-foreground rounded-tr-sm'
            : 'bg-muted text-foreground rounded-tl-sm',
        )}
      >
        {/* Content */}
        {isEmpty && isStreaming ? (
          <TypingIndicator />
        ) : isUser ? (
          <p className="whitespace-pre-wrap leading-relaxed break-words">{message.content}</p>
        ) : (
          <div className="break-words">
            <MarkdownRenderer
              content={message.content}
              className={isUser ? 'text-primary-foreground' : undefined}
            />
            {isStreaming && <TypingCursor />}
          </div>
        )}

        {/* Meta row: model + timestamp */}
        {!isEmpty && (
          <div
            className={cn(
              'mt-1 flex items-center gap-2 text-[10px]',
              isUser ? 'justify-end text-primary-foreground/60' : 'text-muted-foreground',
            )}
          >
            {!isUser && message.model_used && (
              <span className="font-mono truncate max-w-[140px]">{message.model_used}</span>
            )}
            {message.created_at && (
              <span>{formatTime(message.created_at)}</span>
            )}
          </div>
        )}

        {/* Copy button — appears on hover */}
        {!isEmpty && !isStreaming && (
          <button
            onClick={copyContent}
            aria-label="Copy message"
            className={cn(
              'absolute -top-2 flex items-center gap-1 rounded-full border border-border bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground shadow-sm',
              'opacity-0 group-hover/msg:opacity-100 transition-opacity',
              isUser ? 'left-2' : 'right-2',
            )}
          >
            {copied ? <Check className="size-2.5" /> : <Copy className="size-2.5" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        )}
      </div>
    </div>
  )
}
