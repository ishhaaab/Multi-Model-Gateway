import { useCallback, useEffect, useState } from "react";
import { Cpu, RotateCw, Sparkles } from "lucide-react";
import { hardwareApi } from "@/lib/api-endpoints";
import type { CookbookResponse, CookbookVerdict } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";

const CONTEXT_OPTIONS = [2048, 4096, 8192, 16384, 32768];

const VERDICT: Record<CookbookVerdict, { label: string; cls: string }> = {
  fits_fully: { label: "Fits fully", cls: "bg-success/15 text-success" },
  partial_offload: { label: "Partial offload", cls: "bg-accent-secondary/15 text-accent-secondary" },
  wont_fit: { label: "Won't fit", cls: "bg-danger/15 text-danger" },
  cpu_only: { label: "CPU only", cls: "bg-bg-elevated/60 text-text-muted" },
  unknown: { label: "Unknown", cls: "bg-bg-elevated/60 text-text-muted" },
};

function gb(mb: number): string {
  return `${(mb / 1024).toFixed(1)} GB`;
}

export default function CookbookPage() {
  const [contextTokens, setContextTokens] = useState(8192);
  const [data, setData] = useState<CookbookResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async (tokens: number) => {
    setLoading(true);
    setError(false);
    try {
      setData(await hardwareApi.cookbook(tokens));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(contextTokens);
  }, [contextTokens, load]);

  const hw = data?.hardware;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-border px-6 py-4 max-md:pl-14">
        <div>
          <h1 className="text-2xl text-text-primary">Cookbook</h1>
          <p className="text-sm text-text-secondary">Model recommendations for your hardware</p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<RotateCw size={14} />}
          onClick={() => load(contextTokens)}
          isLoading={loading}
        >
          Refresh
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto flex max-w-4xl flex-col gap-5">
          {/* Hardware */}
          <section className="rounded-xl border border-border bg-bg-secondary/60 p-5">
            <h2 className="mb-3 flex items-center gap-2 text-lg text-text-primary">
              <Cpu size={18} className="text-accent-primary" />
              Detected hardware
            </h2>
            {loading && !data ? (
              <Skeleton className="h-12 w-2/3" />
            ) : !hw?.gpu_available || hw.gpus.length === 0 ? (
              <p className="text-sm text-text-muted">
                No GPU detected — recommendations assume CPU-only inference.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {hw.gpus.map((g) => {
                  const usedPct = g.vram_total_mb
                    ? Math.round(((g.vram_total_mb - g.vram_free_mb) / g.vram_total_mb) * 100)
                    : 0;
                  return (
                    <div key={g.index} className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between gap-2 text-sm">
                        <span className="font-medium text-text-primary">{g.name}</span>
                        <span className="font-mono text-[0.8125rem] text-text-secondary">
                          {gb(g.vram_free_mb)} free / {gb(g.vram_total_mb)}
                        </span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-tertiary">
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
          </section>

          {/* Context selector */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Context window (tokens)</label>
            <div className="flex flex-wrap gap-1.5">
              {CONTEXT_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => setContextTokens(n)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-[0.8125rem] transition-colors",
                    contextTokens === n
                      ? "border-accent-primary bg-accent-primary text-white"
                      : "border-border bg-bg-tertiary text-text-secondary hover:text-text-primary"
                  )}
                >
                  {n.toLocaleString()}
                </button>
              ))}
            </div>
          </div>

          {/* Recommendation banner */}
          {data?.recommendation && (
            <div className="flex items-start gap-2 rounded-xl border border-accent-primary/30 bg-accent-primary/10 px-4 py-3">
              <Sparkles size={16} className="mt-0.5 shrink-0 text-accent-primary" />
              <p className="text-sm leading-relaxed text-text-primary">{data.recommendation}</p>
            </div>
          )}

          {/* Model table */}
          {error ? (
            <p className="text-sm text-text-muted">Couldn't load the cookbook. Try refreshing.</p>
          ) : loading && !data ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="bg-bg-tertiary/60 text-left text-[0.75rem] uppercase tracking-wide text-text-muted">
                    <th className="px-3 py-2 font-medium">Model</th>
                    <th className="px-3 py-2 font-medium">Quant</th>
                    <th className="px-3 py-2 font-medium">Needs</th>
                    <th className="px-3 py-2 font-medium">Verdict</th>
                    <th className="px-3 py-2 font-medium">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.models.map((m) => {
                    const v = VERDICT[m.verdict] ?? VERDICT.unknown;
                    return (
                      <tr key={m.id} className="border-t border-border align-top">
                        <td className="px-3 py-2.5">
                          <span className="block font-mono text-[0.8125rem] text-text-primary">{m.id}</span>
                          <span className="text-[0.7rem] text-text-muted">
                            {m.params_b}B · {m.source}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[0.8125rem] text-text-secondary">
                          {m.quant}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[0.8125rem] text-text-secondary">
                          {m.need_gb.toFixed(1)} GB
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={cn("inline-block whitespace-nowrap rounded px-1.5 py-0.5 text-[0.7rem] font-medium", v.cls)}>
                            {v.label}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-[0.8125rem] text-text-muted">{m.rationale}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
