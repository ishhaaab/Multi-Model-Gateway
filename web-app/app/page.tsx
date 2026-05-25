'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { Spinner } from '@/components/ui/spinner'

export default function RootPage() {
  const { isAuthenticated, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (isLoading) return
    if (isAuthenticated) {
      router.replace('/conversations')
    } else {
      router.replace('/login')
    }
  }, [isAuthenticated, isLoading, router])

  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <Spinner className="size-8 text-muted-foreground" />
    </main>
  )
}
