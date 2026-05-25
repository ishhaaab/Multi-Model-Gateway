'use client'

import { useRouter } from 'next/navigation'
import { MessageSquare, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function ConversationsPage() {
  const router = useRouter()

  return (
    <main className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="flex size-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
        <MessageSquare className="size-8" />
      </div>
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-foreground">No conversation selected</h1>
        <p className="text-sm text-muted-foreground max-w-xs text-balance">
          Select a conversation from the sidebar or start a new chat to get going.
        </p>
      </div>
      <Button onClick={() => router.push('/chat/new')} className="gap-2">
        <Plus className="size-4" />
        New Chat
      </Button>
    </main>
  )
}
