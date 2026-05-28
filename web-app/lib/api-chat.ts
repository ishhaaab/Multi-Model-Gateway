import { getAccessToken } from './api'

export interface StreamChatOptions {
  messages: { role: string; content: string }[]
  provider: string
  model: string
  conversationId: string | null
  onToken: (token: string) => void
  onDone: () => void
  onError: (err: Error) => void
  signal?: AbortSignal
}

export async function streamChat(options: StreamChatOptions): Promise<void> {
  const { messages, provider, model, conversationId, onToken, onDone, onError, signal } = options

  const token = getAccessToken()

  let response: Response
  try {
    response = await fetch('/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        messages,
        provider,
        model,
        stream: true,
        conversation_id: conversationId,
      }),
      signal,
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') return
    onError(err instanceof Error ? err : new Error(String(err)))
    return
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body?.error?.message || JSON.stringify(body)
    } catch {}
    onError(new Error(`Error code: ${response.status} - ${detail}`))
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onError(new Error('No response body'))
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // Keep the last (potentially incomplete) line in the buffer
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue

        const rawData = trimmed.slice('data:'.length)
        if (rawData === '[DONE]') {
          onDone()
          return
        }

        // Raw text chunks — pass directly as token
        if (rawData) {
          onToken(rawData)
        }
      }
    }

    // Flush any remaining buffer content
    if (buffer.trim().startsWith('data:')) {
      const rawData = buffer.trim().slice('data:'.length).trim()
      if (rawData === '[DONE]') {
        onDone()
        return
      }
      if (rawData) onToken(rawData)
    }

    onDone()
  } catch (err) {
    if ((err as Error).name === 'AbortError') return
    onError(err instanceof Error ? err : new Error(String(err)))
  } finally {
    reader.releaseLock()
  }
}
