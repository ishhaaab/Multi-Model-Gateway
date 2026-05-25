'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChat } from '@/lib/api-chat'
import { conversationsApi, Message } from '@/lib/api-conversations'

interface SendMessageOptions {
  model: string
  provider: string
  conversationId: string | null
}

interface UseStreamChatReturn {
  messages: Message[]
  isStreaming: boolean
  error: string | null
  sendMessage: (content: string, opts: SendMessageOptions) => Promise<boolean>
  abort: () => void
  clearError: () => void
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>
}

export function useStreamChat(initialConversationId?: string | null): UseStreamChatReturn {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const abortControllerRef = useRef<AbortController | null>(null)
  const completedRef = useRef(false)

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
    setIsStreaming(false)
  }, [])

  const clearError = useCallback(() => setError(null), [])

  const sendMessage = useCallback(
    async (content: string, { model, provider, conversationId }: SendMessageOptions): Promise<boolean> => {
      if (isStreaming) return false

      completedRef.current = false

      // Append user message immediately
      const userMessage: Message = { role: 'user', content }
      setMessages((prev) => [...prev, userMessage])

      // Prepare placeholder for assistant response
      const assistantPlaceholder: Message = { role: 'assistant', content: '' }
      setMessages((prev) => [...prev, assistantPlaceholder])

      setIsStreaming(true)
      setError(null)

      // Build history for the request (everything before the placeholder)
      const history = (await new Promise<Message[]>((resolve) => {
        setMessages((prev) => {
          resolve(prev.slice(0, -1)) // exclude the empty assistant placeholder
          return prev
        })
      }))

      const controller = new AbortController()
      abortControllerRef.current = controller

      await streamChat({
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
          setIsStreaming(false)
        },
        onError: (err) => {
          setError(err.message)
          setIsStreaming(false)
          // Remove empty placeholder on error
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (last?.role === 'assistant' && last.content === '') {
              return prev.slice(0, -1)
            }
            return prev
          })
        },
      })

      return completedRef.current
    },
    [isStreaming],
  )

  return { messages, isStreaming, error, sendMessage, abort, clearError, setMessages }
}
