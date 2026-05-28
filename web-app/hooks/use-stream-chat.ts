'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChat } from '@/lib/api-chat'
import { conversationsApi, Message } from '@/lib/api-conversations'

interface SendMessageOptions {
  model: string
  provider: string
  conversationId: string | null
}

export interface RetryStatus {
  attempt: number
  total: number
}

interface UseStreamChatReturn {
  messages: Message[]
  isStreaming: boolean
  error: string | null
  retryStatus: RetryStatus | null
  sendMessage: (content: string, opts: SendMessageOptions) => Promise<boolean>
  abort: () => void
  clearError: () => void
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>
}

const MAX_RETRIES = 5

function isRetryable(errMessage: string): boolean {
  return errMessage.includes('Error code: 429') || errMessage.includes('Error code: 503')
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

export function useStreamChat(initialConversationId?: string | null): UseStreamChatReturn {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryStatus, setRetryStatus] = useState<RetryStatus | null>(null)

  const abortControllerRef = useRef<AbortController | null>(null)
  const completedRef = useRef(false)
  const retryCancelledRef = useRef(false)

  // Load existing messages when conversationId changes
  useEffect(() => {
    if (!initialConversationId) {
      setMessages([])
      return
    }

    let cancelled = false

    async function loadMessages() {
      try {
        const msgs = await conversationsApi.getMessages(initialConversationId!)
        if (!cancelled) setMessages(msgs)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load messages')
        }
      }
    }

    loadMessages()
    return () => { cancelled = true }
  }, [initialConversationId])

  const abort = useCallback(() => {
    abortControllerRef.current?.abort()
    retryCancelledRef.current = true
    setIsStreaming(false)
    setRetryStatus(null)
  }, [])

  const clearError = useCallback(() => setError(null), [])

  const sendMessage = useCallback(
    async (content: string, { model, provider, conversationId }: SendMessageOptions): Promise<boolean> => {
      if (isStreaming) return false

      completedRef.current = false
      retryCancelledRef.current = false

      // Append user message immediately
      const userMessage: Message = { role: 'user', content }
      setMessages((prev) => [...prev, userMessage])

      setIsStreaming(true)
      setError(null)
      setRetryStatus(null)

      // Build history for the request
      const getHistory = () =>
        new Promise<Message[]>((resolve) => {
          setMessages((prev) => {
            resolve(prev.slice())
            return prev
          })
        })

      const history = await getHistory()

      for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
        if (retryCancelledRef.current) return false

        if (attempt > 1) {
          setRetryStatus({ attempt, total: MAX_RETRIES })
          // Re-add assistant placeholder for the retry
          const placeholder: Message = { role: 'assistant', content: '' }
          setMessages((prev) => [...prev, placeholder])
        }

        const controller = new AbortController()
        abortControllerRef.current = controller

        try {
          await new Promise<void>((resolve, reject) => {
            streamChat({
              messages: history.map(({ role, content }) => ({ role, content })),
              provider,
              model,
              conversationId,
              signal: controller.signal,
              onToken: (token) => {
                setMessages((prev) => {
                  const next = [...prev]
                  const last = next[next.length - 1]
                  if (last?.role === 'assistant') {
                    next[next.length - 1] = { ...last, content: last.content + token }
                  }
                  return next
                })
              },
              onDone: () => {
                completedRef.current = true
                resolve()
              },
              onError: (err) => {
                reject(err)
              },
            })
          })

          // Success
          completedRef.current = true
          setIsStreaming(false)
          setRetryStatus(null)
          return true
        } catch (err) {
          const errMessage = err instanceof Error ? err.message : String(err)

          // Remove empty assistant placeholder on failure
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (last?.role === 'assistant' && last.content === '') {
              return prev.slice(0, -1)
            }
            return prev
          })

          if (isRetryable(errMessage) && attempt < MAX_RETRIES && !retryCancelledRef.current) {
            const delay = 2000 * attempt
            await sleep(delay)
            continue
          }

          // Final failure
          setError(errMessage)
          setIsStreaming(false)
          setRetryStatus(null)
          return false
        }
      }

      return false
    },
    [isStreaming],
  )

  return { messages, isStreaming, error, retryStatus, sendMessage, abort, clearError, setMessages }
}
