import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Cpu, RotateCw } from "lucide-react";
import { hfApi, hardwareApi } from "@/lib/api-endpoints";
import type { HardwareInfo, HfCookbookResponse, HfModelDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { ModelList } from "@/components/models/ModelList";
import { ModelDetail } from "@/components/models/ModelDetail";
import { LocalModels } from "@/components/models/LocalModels";

const DEFAULT_CONTEXT = 8192;

type Tab = "local" | "cloud";

function gb(mb: number): string {
  return `${(mb / 1024).toFixed(1)} GB`;
}

export default function ModelsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedRepo = searchParams.get("repo");

  // Top-level tabs — the Models window unifies the old Cookbook page (Local:
  // installed models + fit check) and the HF model browser (Cloud) under one
  // page with a shared hardware strip pinned at the bottom.
  const [tab, setTab] = useState<Tab>("local");
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  // Bottom hardware strip — fetched once on mount and again on Refresh.
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);
  const [hardwareLoading, setHardwareLoading] = useState(true);

  // Cloud tab — left pane (catalog list)
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(10);
  const [contextTokens, setContextTokens] = useState(DEFAULT_CONTEXT);
  const [listData, setListData] = useState<HfCookbookResponse | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listPending, setListPending] = useState(false);
  const [listError, setListError] = useState(false);

  // Cloud tab — right pane (model detail)
  const [detail, setDetail] = useState<HfModelDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState(false);

  // Monotonic request ids — a stale response (older search/repo) is dropped.
  const listSeq = useRef(0);
  const detailSeq = useRef(0);
  // URL-driven repo changes clear the detail during render (React's
  // adjust-state-when-props-change pattern) so the previous repo's detail
  // never paints under the new selection; context-token refetches keep it.
  const [prevRepo, setPrevRepo] = useState(selectedRepo);
  if (prevRepo !== selectedRepo) {
    setPrevRepo(selectedRepo);
    setDetail(null);
    setDetailLoading(true);
    setDetailError(false);
  }

  const loadList = useCallback((q: string, lim: number, tokens: number) => {
    const seq = ++listSeq.current;
    return hfApi
      .models(q, lim, tokens)
      .then((res) => {
        if (seq !== listSeq.current) return;
        setListData(res);
        setListError(false);
      })
      .catch(() => {
        if (seq === listSeq.current) setListError(true);
      })
      .finally(() => {
        if (seq === listSeq.current) {
          setListLoading(false);
          setListPending(false);
        }
      });
  }, []);

  const loadDetail = useCallback((repoId: string, tokens: number): Promise<void> => {
    if (!repoId) return Promise.resolve();
    const seq = ++detailSeq.current;
    return hfApi
      .detail(repoId, tokens)
      .then((res) => {
        if (seq !== detailSeq.current) return;
        setDetail(res);
        setDetailError(false);
      })
      .catch(() => {
        if (seq === detailSeq.current) {
          // The latest request failed — drop any stale detail so the error
          // state renders instead of silently showing out-of-date data.
          setDetail(null);
          setDetailError(true);
        }
      })
      .finally(() => {
        if (seq === detailSeq.current) setDetailLoading(false);
      });
  }, []);

  // setState only ever runs in promise callbacks — the mount effect below
  // never sets state synchronously (react-hooks/set-state-in-effect safe).
  const loadHardware = useCallback(() => {
    return hardwareApi
      .hardware()
      .then((res) => setHardware(res))
      .catch(() => {
        // A failed probe keeps whatever was last detected; the strip only
        // reads as "No GPU detected" when nothing has ever loaded.
      })
      .finally(() => setHardwareLoading(false));
  }, []);

  useEffect(() => {
    void loadList(query, limit, contextTokens);
  }, [query, limit, contextTokens, loadList]);

  useEffect(() => {
    void loadDetail(selectedRepo ?? "", contextTokens);
  }, [selectedRepo, contextTokens, loadDetail]);

  useEffect(() => {
    void loadHardware();
  }, [loadHardware]);

  const handleSearch = () => {
    const q = search.trim();
    setListError(false);
    setListLoading(true);
    setListPending(true);
    if (q === query) {
      // Same query — the list effect won't re-fire, so fetch directly.
      void loadList(q, limit, contextTokens);
    } else {
      setQuery(q);
    }
  };

  const handleRetryList = () => {
    setListError(false);
    setListLoading(true);
    setListPending(true);
    void loadList(query, limit, contextTokens);
  };

  const handleRetryDetail = () => {
    setDetailLoading(true);
    setDetailError(false);
    void loadDetail(selectedRepo ?? "", contextTokens);
  };

  const handleContextChange = (tokens: number) => {
    // Keep the current detail visible but flip loading on — the pane shows
    // the refreshing indicator instead of presenting stale fit data as fresh.
    setContextTokens(tokens);
    setDetailLoading(true);
    setDetailError(false);
  };

  const handleSelect = (repoId: string) => {
    // Clear immediately so the old repo's detail never paints under the new
    // selection; the effect refetches once the URL lands.
    setDetail(null);
    setDetailLoading(true);
    setDetailError(false);
    if (repoId === selectedRepo) {
      // Same repo — the URL won't change, so the detail effect won't re-fire.
      void loadDetail(repoId, contextTokens);
    } else {
      setSearchParams({ repo: repoId });
    }
  };

  // Refresh refetches the active tab + the bottom hardware strip.
  const refresh = () => {
    setRefreshing(true);
    setHardwareLoading(true);
    const jobs: Array<Promise<unknown>> = [loadHardware()];
    if (tab === "local") {
      // LocalModels refetches itself when refreshKey increments.
      setRefreshKey((k) => k + 1);
    } else {
      setListLoading(true);
      setListPending(true);
      jobs.push(loadList(query, limit, contextTokens));
      if (selectedRepo) {
        setDetailLoading(true);
        setDetailError(false);
        jobs.push(loadDetail(selectedRepo, contextTokens));
      }
    }
    void Promise.allSettled(jobs).then(() => setRefreshing(false));
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-border px-6 py-4 max-md:pl-14">
        <div>
          <h1 className="text-2xl text-text-primary">Models</h1>
          <p className="text-sm text-text-secondary">
            Installed models and the Hugging Face catalog — fit-checked against your hardware
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<RotateCw size={14} />}
          onClick={refresh}
          isLoading={refreshing}
        >
          Refresh
        </Button>
      </header>

      {/* Tab control — Local | Cloud */}
      <div className="flex flex-wrap gap-1.5 border-b border-border px-6 py-3">
        {(
          [
            { id: "local", label: "Local" },
            { id: "cloud", label: "Cloud" },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "rounded-lg border px-3 py-1.5 text-[0.8125rem] transition-colors",
              tab === t.id
                ? "border-accent-primary bg-accent-primary text-white"
                : "border-border bg-bg-tertiary text-text-secondary hover:text-text-primary"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Scrollable body — renders the active tab; the hardware strip below is
          pinned so it stays visible while this area scrolls. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "cloud" ? (
          <div className="grid h-full min-h-0 grid-cols-[minmax(320px,380px)_1fr] max-lg:grid-cols-1 max-lg:overflow-y-auto">
            <div className="min-h-0 overflow-y-auto border-r border-border max-lg:overflow-visible max-lg:border-r-0 max-lg:border-b">
              <ModelList
                models={listData?.models ?? []}
                loading={listLoading}
                pending={listPending}
                error={listError}
                search={search}
                onSearchChange={setSearch}
                limit={limit}
                onLimitChange={setLimit}
                onSubmit={handleSearch}
                onRetry={handleRetryList}
                selectedRepo={selectedRepo}
                onSelect={handleSelect}
              />
            </div>
            <div className="min-h-0 overflow-y-auto max-lg:overflow-visible">
              <ModelDetail
                repoId={selectedRepo}
                detail={detail}
                loading={detailLoading}
                error={detailError}
                contextTokens={contextTokens}
                onContextChange={handleContextChange}
                onRetry={handleRetryDetail}
              />
            </div>
          </div>
        ) : (
          <LocalModels refreshKey={refreshKey} />
        )}
      </div>

      {/* Bottom hardware strip — compact single row, persistent across tabs */}
      <footer className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-border bg-bg-secondary/40 px-6 py-2.5">
        <span className="flex shrink-0 items-center gap-1.5 text-[0.7rem] font-medium uppercase tracking-wide text-text-muted">
          <Cpu size={13} className="text-accent-primary" />
          Detected hardware
        </span>
        {hardwareLoading && !hardware ? (
          <Skeleton className="h-5 w-64" />
        ) : !hardware?.gpu_available || hardware.gpus.length === 0 ? (
          <span className="text-[0.8125rem] text-text-muted">No GPU detected</span>
        ) : (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5">
            {hardware.gpus.map((g) => {
              const usedPct = g.vram_total_mb
                ? Math.round(((g.vram_total_mb - g.vram_free_mb) / g.vram_total_mb) * 100)
                : 0;
              return (
                <div key={g.index} className="flex min-w-0 items-center gap-2">
                  <span
                    className="max-w-[240px] truncate text-[0.8125rem] font-medium text-text-primary"
                    title={g.name}
                  >
                    {g.name}
                  </span>
                  <span className="whitespace-nowrap font-mono text-[0.75rem] text-text-secondary">
                    {gb(g.vram_free_mb)} free / {gb(g.vram_total_mb)}
                  </span>
                  <div className="h-1 w-16 shrink-0 overflow-hidden rounded-full bg-bg-tertiary">
                    <div
                      className="h-full rounded-full bg-accent-primary"
                      style={{ width: `${usedPct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </footer>
    </div>
  );
}
