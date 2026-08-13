import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Cpu, RotateCw, Search, Sparkles } from "lucide-react";
import { hardwareApi, hfApi } from "@/lib/api-endpoints";
import type { CookbookModel, CookbookResponse, CookbookVerdict, HfCookbookResponse, HfModelEntry } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";

const CONTEXT_OPTIONS = [2048, 4096, 8192, 16384, 32768];
const HF_LIMIT_OPTIONS = [10, 25, 50];

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

type Tab = "local" | "hf";

interface ModelTableProps {
  models: Array<CookbookModel | HfModelEntry>;
  sublabel: (m: CookbookModel | HfModelEntry) => string;
  quantLabel: (m: CookbookModel | HfModelEntry) => string;
  notes: (m: CookbookModel | HfModelEntry) => string;
  /** When provided, rows become clickable (HF tab → model browser). */
  onRowClick?: (m: CookbookModel | HfModelEntry) => void;
}

/** Shared table so both tabs compare apples-to-apples (same columns). */
function ModelTable({ models, sublabel, quantLabel, notes, onRowClick }: ModelTableProps) {
  return (
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
          {models.map((m) => {
            const v = VERDICT[m.verdict] ?? VERDICT.unknown;
            return (
              <tr
                key={m.id}
                onClick={onRowClick ? () => onRowClick(m) : undefined}
                className={cn(
                  "border-t border-border align-top",
                  onRowClick && "cursor-pointer transition-colors hover:bg-bg-tertiary/40"
                )}
              >
                <td className="px-3 py-2.5">
                  <span className="block font-mono text-[0.8125rem] text-text-primary">{m.id}</span>
                  <span className="text-[0.7rem] text-text-muted">{sublabel(m)}</span>
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[0.8125rem] text-text-secondary">
                  {quantLabel(m)}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[0.8125rem] text-text-secondary">
                  {m.need_gb != null ? `${m.need_gb.toFixed(1)} GB` : "—"}
                </td>
                <td className="px-3 py-2.5">
                  <span className={cn("inline-block whitespace-nowrap rounded px-1.5 py-0.5 text-[0.7rem] font-medium", v.cls)}>
                    {v.label}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-[0.8125rem] text-text-muted">{notes(m)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function CookbookPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("local");
  const [contextTokens, setContextTokens] = useState(8192);

  // local cookbook (/v1/cookbook)
  const [data, setData] = useState<CookbookResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // hugging face cookbook (/v1/hf/models)
  const [hfSearch, setHfSearch] = useState(""); // input value
  const [hfQuery, setHfQuery] = useState("");   // last submitted search
  const [hfLimit, setHfLimit] = useState(10);
  const [hfData, setHfData] = useState<HfCookbookResponse | null>(null);
  const [hfLoading, setHfLoading] = useState(false);
  const [hfError, setHfError] = useState(false);

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

  const loadHf = useCallback(async (tokens: number, query: string, limit: number) => {
    setHfLoading(true);
    setHfError(false);
    try {
      setHfData(await hfApi.models(query, limit, tokens));
    } catch {
      setHfError(true);
    } finally {
      setHfLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(contextTokens);
  }, [contextTokens, load]);

  // load the HF catalog on tab switch, search submit, limit change, or context change
  useEffect(() => {
    if (tab === "hf") {
      void loadHf(contextTokens, hfQuery, hfLimit);
    }
  }, [tab, contextTokens, hfQuery, hfLimit, loadHf]);

  const hw = data?.hardware ?? hfData?.hardware;

  const localSublabel = (m: CookbookModel | HfModelEntry) =>
    `${(m as CookbookModel).params_b}B · ${m.source}`;
  const localQuant = (m: CookbookModel | HfModelEntry) => (m as CookbookModel).quant;
  const localNotes = (m: CookbookModel | HfModelEntry) => m.rationale;

  const hfSublabel = (m: CookbookModel | HfModelEntry) => {
    const hf = m as HfModelEntry;
    const parts: string[] = [];
    if (hf.params_b != null) parts.push(`${hf.params_b}B`);
    parts.push("HF");
    if (hf.downloads != null) parts.push(`${hf.downloads.toLocaleString()} downloads`);
    if (hf.likes != null) parts.push(`${hf.likes.toLocaleString()} likes`);
    return parts.join(" · ");
  };
  const hfNotes = (m: CookbookModel | HfModelEntry) => {
    const hf = m as HfModelEntry;
    return hf.pipeline_tag ? `${m.rationale} · ${hf.pipeline_tag}` : m.rationale;
  };

  const refresh = () => {
    if (tab === "hf") void loadHf(contextTokens, hfQuery, hfLimit);
    else void load(contextTokens);
  };

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
          onClick={refresh}
          isLoading={tab === "hf" ? hfLoading : loading}
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
            {(loading || hfLoading) && !hw ? (
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

          {/* Source tabs */}
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                { id: "local", label: "Local Models" },
                { id: "hf", label: "Hugging Face Models" },
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

          {/* Recommendation banner (local tab only — HF has no recommendation) */}
          {tab === "local" && data?.recommendation && (
            <div className="flex items-start gap-2 rounded-xl border border-accent-primary/30 bg-accent-primary/10 px-4 py-3">
              <Sparkles size={16} className="mt-0.5 shrink-0 text-accent-primary" />
              <p className="text-sm leading-relaxed text-text-primary">{data.recommendation}</p>
            </div>
          )}

          {tab === "hf" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setHfQuery(hfSearch.trim());
              }}
              className="flex flex-col gap-2 sm:flex-row sm:items-center"
            >
              <input
                type="text"
                value={hfSearch}
                onChange={(e) => setHfSearch(e.target.value)}
                placeholder="Search Hugging Face models… e.g. qwen, llama"
                className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-bg-tertiary px-3 text-[0.8125rem] text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-accent-primary"
              />
              <select
                value={hfLimit}
                onChange={(e) => setHfLimit(Number(e.target.value))}
                className="h-9 rounded-lg border border-border bg-bg-tertiary px-3 text-[0.8125rem] text-text-secondary outline-none transition-colors focus:border-accent-primary"
              >
                {HF_LIMIT_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n} results
                  </option>
                ))}
              </select>
              <Button type="submit" size="sm" leftIcon={<Search size={14} />} isLoading={hfLoading}>
                Search
              </Button>
            </form>
          )}

          {/* Model table */}
          {tab === "local" ? (
            error ? (
              <p className="text-sm text-text-muted">Couldn't load the cookbook. Try refreshing.</p>
            ) : loading && !data ? (
              <div className="flex flex-col gap-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : data && data.models.length === 0 ? (
              <p className="text-sm text-text-muted">No local models found.</p>
            ) : (
              <ModelTable
                models={data?.models ?? []}
                sublabel={localSublabel}
                quantLabel={localQuant}
                notes={localNotes}
              />
            )
          ) : hfError ? (
            <div className="flex items-center justify-between gap-2 rounded-xl border border-border bg-bg-tertiary/50 px-4 py-3">
              <span className="text-sm text-text-muted">Couldn't load Hugging Face models.</span>
              <button
                onClick={() => loadHf(contextTokens, hfQuery, hfLimit)}
                className="flex items-center gap-1 text-[0.8125rem] text-accent-primary hover:underline"
              >
                <RotateCw size={13} /> Retry
              </button>
            </div>
          ) : hfLoading && !hfData ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : hfData && hfData.models.length === 0 ? (
            <p className="text-sm text-text-muted">No models found — try a different search.</p>
          ) : (
            <ModelTable
              models={hfData?.models ?? []}
              sublabel={hfSublabel}
              quantLabel={() => "—"}
              notes={hfNotes}
              onRowClick={(m) => navigate(`/models?repo=${encodeURIComponent(m.id)}`)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
