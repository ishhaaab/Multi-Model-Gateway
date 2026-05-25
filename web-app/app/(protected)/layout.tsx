'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { conversationsApi, type Conversation } from '@/lib/api-conversations'
import { AppSidebar } from '@/components/app-sidebar'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { Spinner } from '@/components/ui/spinner'

export default function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  const router = useRouter()

  const [conversations, setConversations] = useState<Conversation[]>([])
  const [convosLoading, setConvosLoading] = useState(true)

  // Auth guard
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/login')
    }
  }, [isAuthenticated, isLoading, router])

  const loadConversations = useCallback(async () => {
    try {
      const data = await conversationsApi.list()
      // Sort newest first
      setConversations(data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
    } catch {
      // Silently fail — sidebar will show empty state
    } finally {
      setConvosLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isAuthenticated) {
      loadConversations()
    }
  }, [isAuthenticated, loadConversations])

  if (isLoading) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-background">
        <Spinner className="size-8 text-muted-foreground" />
      </div>
    )
  }

  if (!isAuthenticated) return null

  return (
    <SidebarProvider>
      <AppSidebar
        conversations={conversations}
        isLoading={convosLoading}
        onConversationsChange={setConversations}
      />
      <SidebarInset className="flex flex-col h-svh overflow-hidden">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-4">
          <SidebarTrigger className="-ml-1" />
        </header>
        <div className="flex flex-col flex-1 min-h-0">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
