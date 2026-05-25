'use client'

import { useRouter } from 'next/navigation'
import { useCallback } from 'react'
import { ChatView } from '@/components/chat-view'
import { conversationsApi } from '@/lib/api-conversations'

export default function NewChatPage() {
  const router = useRouter()

  // Called after the first message streams in.
  // Refresh conversation list and navigate to the new conversation.
  const handleNewConversation = useCallback(async () => {
    try {
      const convos = await conversationsApi.list()
      if (convos.length > 0) {
        // Newest conversation will be first after sorting by created_at desc
        const sorted = convos.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        )
        router.replace(`/chat/${sorted[0].id}`)
      }
    } catch {
      // Navigation failure is non-critical; user can still see the chat
    }
  }, [router])

  return <ChatView conversationId={null} onNewConversation={handleNewConversation} />
}
