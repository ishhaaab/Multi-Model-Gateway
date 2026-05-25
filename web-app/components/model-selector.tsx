'use client'

import { useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { modelsApi, type LocalModel, type OpenRouterModel } from '@/lib/api-models'
import { cn } from '@/lib/utils'

// ─── Provider options ─────────────────────────────────────────────────────────

const PROVIDERS = [
  {
    value: 'auto',
    label: 'Auto',
    description: 'Backend decides based on message content',
  },
  {
    value: 'local',
    label: 'Local',
    description: 'Forces LM Studio (local model)',
  },
  {
    value: 'openrouter',
    label: 'OpenRouter',
    description: 'Forces OpenRouter API',
  },
]

// ─── Props ────────────────────────────────────────────────────────────────────

interface ModelSelectorProps {
  open: boolean
  onClose: () => void
  selectedModel: string
  selectedProvider: string
  onSelect: (model: string, provider: string) => void
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ModelSelector({
  open,
  onClose,
  selectedModel,
  selectedProvider,
  onSelect,
}: ModelSelectorProps) {
  const [localModels, setLocalModels] = useState<LocalModel[]>([])
  const [orModels, setOrModels] = useState<OpenRouterModel[]>([])
  const [localLoading, setLocalLoading] = useState(false)
  const [orLoading, setOrLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<string>(selectedProvider === 'openrouter' ? 'openrouter' : 'local')

  useEffect(() => {
    if (!open) return
    // Load local models
    setLocalLoading(true)
    modelsApi.getLocalModels()
      .then(({ data }) => setLocalModels(data))
      .catch(() => setLocalModels([]))
      .finally(() => setLocalLoading(false))

    // Load OpenRouter models
    setOrLoading(true)
    modelsApi.getOpenRouterModels()
      .then(({ data }) => setOrModels(data))
      .catch(() => setOrModels([]))
      .finally(() => setOrLoading(false))
  }, [open])

  function selectModel(modelId: string, provider: string) {
    onSelect(modelId, provider)
    onClose()
  }

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="right" className="w-full sm:w-96 flex flex-col gap-0 p-0">
        <SheetHeader className="px-4 py-4 border-b border-border">
          <SheetTitle>Select Model</SheetTitle>
        </SheetHeader>

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex flex-col flex-1 min-h-0"
        >
          {/* Tab triggers */}
          <div className="px-4 pt-3 pb-2 border-b border-border">
            {/* Provider selection */}
            <div className="mb-3 space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Routing
              </p>
              {PROVIDERS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => {
                    onSelect(selectedModel, p.value)
                  }}
                  className={cn(
                    'w-full flex items-start gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors',
                    selectedProvider === p.value
                      ? 'bg-accent text-accent-foreground'
                      : 'hover:bg-muted text-muted-foreground',
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <span className="font-medium text-foreground">{p.label}</span>
                    <span className="block text-xs text-muted-foreground mt-0.5">
                      {p.description}
                    </span>
                  </div>
                  {selectedProvider === p.value && (
                    <Check className="size-4 shrink-0 mt-0.5 text-primary" />
                  )}
                </button>
              ))}
            </div>

            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Model
            </p>
            <TabsList className="w-full">
              <TabsTrigger value="local" className="flex-1">Local</TabsTrigger>
              <TabsTrigger value="openrouter" className="flex-1">OpenRouter</TabsTrigger>
            </TabsList>
          </div>

          {/* Local models */}
          <TabsContent value="local" className="flex-1 min-h-0 mt-0">
            <ScrollArea className="h-full">
              <div className="p-2 space-y-0.5">
                {localLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="size-5 animate-spin text-muted-foreground" />
                  </div>
                ) : localModels.length === 0 ? (
                  <p className="px-2 py-6 text-center text-sm text-muted-foreground">
                    No local models found. Is LM Studio running?
                  </p>
                ) : (
                  localModels.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => selectModel(m.id, 'local')}
                      className={cn(
                        'w-full flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors',
                        selectedModel === m.id && selectedProvider === 'local'
                          ? 'bg-accent text-accent-foreground'
                          : 'hover:bg-muted text-foreground',
                      )}
                    >
                      <span className="flex-1 font-mono truncate text-xs">{m.id}</span>
                      {selectedModel === m.id && selectedProvider === 'local' && (
                        <Check className="size-4 shrink-0 text-primary" />
                      )}
                    </button>
                  ))
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          {/* OpenRouter models */}
          <TabsContent value="openrouter" className="flex-1 min-h-0 mt-0">
            <ScrollArea className="h-full">
              <div className="p-2 space-y-0.5">
                {orLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="size-5 animate-spin text-muted-foreground" />
                  </div>
                ) : orModels.length === 0 ? (
                  <p className="px-2 py-6 text-center text-sm text-muted-foreground">
                    No OpenRouter models available.
                  </p>
                ) : (
                  orModels.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => selectModel(m.id, 'openrouter')}
                      className={cn(
                        'w-full flex items-start gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors',
                        selectedModel === m.id && selectedProvider === 'openrouter'
                          ? 'bg-accent text-accent-foreground'
                          : 'hover:bg-muted text-foreground',
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <span className="block font-medium text-sm truncate">{m.name}</span>
                        <span className="block font-mono text-[10px] text-muted-foreground truncate">{m.id}</span>
                      </div>
                      {selectedModel === m.id && selectedProvider === 'openrouter' && (
                        <Check className="size-4 shrink-0 text-primary mt-0.5" />
                      )}
                    </button>
                  ))
                )}
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
