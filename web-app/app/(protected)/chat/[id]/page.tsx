'use client'

import { use } from 'react'
import { ChatView } from '@/components/chat-view'

interface Props {
  params: Promise<{ id: string }>
}

export default function ChatPage({ params }: Props) {
  const { id } = use(params)
  return <ChatView conversationId={id} />
}
