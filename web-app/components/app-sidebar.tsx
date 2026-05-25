'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { toast } from 'sonner'
import {
  MessageSquare,
  Plus,
  Search,
  Trash2,
  Pencil,
  MoreHorizontal,
  LogOut,
  Check,
  X,
} from 'lucide-react'

import { conversationsApi, type Conversation } from '@/lib/api-conversations'
import { useAuth } from '@/lib/auth-context'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInput,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from '@/components/ui/sidebar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = Date.now()
  const diffMs = now - date.getTime()
  const diffSecs = Math.floor(diffMs / 1000)
  if (diffSecs < 60) return 'just now'
  const diffMins = Math.floor(diffSecs / 60)
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

function initials(email: string): string {
  return email.slice(0, 2).toUpperCase()
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface AppSidebarProps {
  conversations: Conversation[]
  isLoading: boolean
  onConversationsChange: (convos: Conversation[]) => void
}

// ─── Rename input ─────────────────────────────────────────────────────────────

function RenameInput({
  convo,
  onDone,
}: {
  convo: Conversation
  onDone: (newTitle: string | null) => void
}) {
  const [value, setValue] = React.useState(convo.title)
  const inputRef = React.useRef<HTMLInputElement>(null)

  React.useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  function commit() {
    const trimmed = value.trim()
    if (trimmed && trimmed !== convo.title) {
      onDone(trimmed)
    } else {
      onDone(null)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') commit()
    if (e.key === 'Escape') onDone(null)
  }

  return (
    <div className="flex items-center gap-1 w-full px-1">
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={handleKeyDown}
        className="flex-1 min-w-0 bg-sidebar-accent text-sidebar-accent-foreground rounded px-2 py-0.5 text-sm outline-none ring-1 ring-sidebar-ring"
        aria-label="Rename conversation"
      />
      <button
        onMouseDown={(e) => { e.preventDefault(); commit() }}
        className="shrink-0 text-sidebar-foreground hover:text-sidebar-accent-foreground"
        aria-label="Confirm rename"
      >
        <Check className="size-3.5" />
      </button>
      <button
        onMouseDown={(e) => { e.preventDefault(); onDone(null) }}
        className="shrink-0 text-sidebar-foreground hover:text-sidebar-accent-foreground"
        aria-label="Cancel rename"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function AppSidebar({ conversations, isLoading, onConversationsChange }: AppSidebarProps) {
  const router = useRouter()
  const pathname = usePathname()
  const { logout } = useAuth()

  const [search, setSearch] = React.useState('')
  const [renamingId, setRenamingId] = React.useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = React.useState<Conversation | null>(null)
  const [isDeleting, setIsDeleting] = React.useState(false)

  // Extract the active conversation id from /chat/[id]
  const activeId = pathname.startsWith('/chat/') ? pathname.split('/')[2] : null

  const filtered = React.useMemo(() => {
    if (!search.trim()) return conversations
    return conversations.filter((c) =>
      c.title.toLowerCase().includes(search.toLowerCase()),
    )
  }, [conversations, search])

  // Auth: extract email from localStorage token payload (best-effort)
  const userEmail = React.useMemo(() => {
    if (typeof window === 'undefined') return ''
    try {
      const token = localStorage.getItem('access_token')
      if (!token) return ''
      const payload = JSON.parse(atob(token.split('.')[1]))
      return payload.sub ?? payload.email ?? ''
    } catch {
      return ''
    }
  }, [])

  async function handleNewChat() {
    router.push('/chat/new')
  }

  async function handleRename(convo: Conversation, newTitle: string) {
    try {
      await conversationsApi.rename(convo.id, newTitle)
      onConversationsChange(
        conversations.map((c) => (c.id === convo.id ? { ...c, title: newTitle } : c)),
      )
    } catch {
      toast.error('Failed to rename conversation')
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      await conversationsApi.delete(deleteTarget.id)
      onConversationsChange(conversations.filter((c) => c.id !== deleteTarget.id))
      // If currently viewing the deleted convo, go back to /conversations
      if (activeId === deleteTarget.id) {
        router.push('/conversations')
      }
      toast.success('Conversation deleted')
    } catch {
      toast.error('Failed to delete conversation')
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }

  async function handleLogout() {
    try {
      await logout()
      router.push('/login')
    } catch {
      toast.error('Logout failed')
    }
  }

  return (
    <>
      <Sidebar collapsible="offcanvas">
        {/* ── Header ── */}
        <SidebarHeader className="gap-3 p-3">
          <div className="flex items-center gap-2">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
              <MessageSquare className="size-4" />
            </div>
            <span className="font-semibold text-sm tracking-tight text-sidebar-foreground">
              LLM Gateway
            </span>
          </div>
          <Button
            size="sm"
            className="w-full justify-start gap-2"
            onClick={handleNewChat}
          >
            <Plus className="size-4" />
            New Chat
          </Button>
        </SidebarHeader>

        {/* ── Search ── */}
        <div className="px-3 pb-1">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
            <SidebarInput
              placeholder="Search conversations..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
              aria-label="Search conversations"
            />
          </div>
        </div>

        {/* ── Conversation list ── */}
        <SidebarContent>
          <SidebarGroup className="p-2">
            <SidebarGroupContent>
              <SidebarMenu>
                {isLoading ? (
                  Array.from({ length: 6 }).map((_, i) => (
                    <SidebarMenuItem key={i}>
                      <SidebarMenuSkeleton showIcon />
                    </SidebarMenuItem>
                  ))
                ) : filtered.length === 0 ? (
                  <div className="px-2 py-6 text-center">
                    <p className="text-xs text-muted-foreground">
                      {search ? 'No matching conversations' : 'No conversations yet'}
                    </p>
                    {!search && (
                      <button
                        onClick={handleNewChat}
                        className="mt-2 text-xs text-sidebar-primary underline-offset-2 hover:underline"
                      >
                        Start your first chat
                      </button>
                    )}
                  </div>
                ) : (
                  filtered.map((convo) => (
                    <SidebarMenuItem key={convo.id}>
                      {renamingId === convo.id ? (
                        <RenameInput
                          convo={convo}
                          onDone={(newTitle) => {
                            if (newTitle) handleRename(convo, newTitle)
                            setRenamingId(null)
                          }}
                        />
                      ) : (
                        <>
                          <SidebarMenuButton
                            isActive={activeId === convo.id}
                            onClick={() => router.push(`/chat/${convo.id}`)}
                            className="group/item pr-8"
                          >
                            <MessageSquare className="shrink-0" />
                            <div className="flex flex-col min-w-0 flex-1">
                              <span className="truncate text-sm leading-tight">
                                {convo.title}
                              </span>
                              <span className={cn(
                                'text-xs truncate',
                                activeId === convo.id
                                  ? 'text-sidebar-accent-foreground/70'
                                  : 'text-muted-foreground',
                              )}>
                                {relativeTime(convo.created_at)}
                              </span>
                            </div>
                          </SidebarMenuButton>

                          <SidebarMenuAction showOnHover asChild>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <button
                                  aria-label="Conversation options"
                                  className="flex items-center justify-center"
                                >
                                  <MoreHorizontal className="size-4" />
                                </button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent side="right" align="start" className="w-40">
                                <DropdownMenuItem onClick={() => setRenamingId(convo.id)}>
                                  <Pencil className="size-4" />
                                  Rename
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  variant="destructive"
                                  onClick={() => setDeleteTarget(convo)}
                                >
                                  <Trash2 className="size-4" />
                                  Delete
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </SidebarMenuAction>
                        </>
                      )}
                    </SidebarMenuItem>
                  ))
                )}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        {/* ── Footer / user ── */}
        <SidebarFooter className="p-2">
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    size="lg"
                    className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                  >
                    <Avatar className="size-7 rounded-md">
                      <AvatarFallback className="rounded-md text-xs bg-sidebar-primary text-sidebar-primary-foreground">
                        {userEmail ? initials(userEmail) : 'U'}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex flex-col min-w-0 flex-1 text-left">
                      <span className="truncate text-xs font-medium">
                        {userEmail || 'Account'}
                      </span>
                    </div>
                    <MoreHorizontal className="shrink-0 size-4 ml-auto" />
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  side="top"
                  align="start"
                  className="w-52"
                >
                  <DropdownMenuItem onClick={handleLogout}>
                    <LogOut className="size-4" />
                    Log out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>

      {/* ── Delete confirmation dialog ── */}
      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete conversation</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete{' '}
              <span className="font-medium text-foreground">
                &ldquo;{deleteTarget?.title}&rdquo;
              </span>
              ? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={isDeleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={isDeleting}>
              {isDeleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
