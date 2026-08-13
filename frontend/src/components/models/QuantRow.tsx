import type { ReactNode } from "react";
import { Download, X } from "lucide-react";
import type { HfFitVerdict, HfQuantOption } from "@/lib/types";
import { cn, truncate } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

// Fit-verdict badge map (mirrors the cookbook's verdict colors: green fits,
// amber offload, red too large, muted unknown/cpu-only).
const FIT_VERDICT: Record<HfFitVerdict, { label: string; cls: string; icon?: ReactNode }> = {
  fits_fully: { label: "Fits fully", cls: "bg-success/15 text-success" },
  fits_cpu_offload: {
    label: "Fits with CPU offload",
    cls: "bg-accent-secondary/15 text-accent-secondary",
  },
  likely_too_large: {
    label: "Likely too large",
    cls: "bg-danger/15 text-danger",
    icon: <X size={12} />,
  },
  cpu_only: { label: "CPU only", cls: "bg-bg-elevated/60 text-text-muted" },
  unknown: { label: "Unknown", cls: "bg-bg-elevated/60 text-text-muted" },
};

/** Base GGUF filename without extension / shard numbering, truncated. */
function shortName(filenames: string[]): string {
  const first = filenames[0] ?? "";
  const base = first.replace(/\.gguf$/i, "").replace(/-\d{5}-of-\d{5}$/i, "");
  return truncate(base.split("/").pop() ?? base, 36);
}

interface QuantRowProps {
  quant: HfQuantOption;
}

export function QuantRow({ quant }: QuantRowProps) {
  const verdict = FIT_VERDICT[quant.fit.verdict] ?? FIT_VERDICT.unknown;

  return (
    <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-bg-secondary/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>GGUF</Badge>
        <span
          className="min-w-0 font-mono text-[0.8125rem] text-text-primary"
          title={quant.filenames[0]}
        >
          {shortName(quant.filenames)}
        </span>
        {quant.is_sharded && quant.filenames.length > 1 && (
          <span className="text-[0.7rem] text-text-muted">{quant.filenames.length} shards</span>
        )}
        <span className="rounded bg-bg-tertiary px-1.5 py-0.5 font-mono text-[0.7rem] text-text-secondary">
          {quant.quant}
        </span>
        <span className="font-mono text-[0.8125rem] text-text-secondary">
          {(quant.size_bytes / 1e9).toFixed(2)} GB
        </span>
        <span
          className={cn(
            "inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-[0.7rem] font-medium",
            verdict.cls
          )}
        >
          {verdict.icon}
          {verdict.label}
        </span>
        <span className="ml-auto flex items-center gap-1.5" title="Download coming soon">
          <Button size="sm" variant="secondary" disabled leftIcon={<Download size={14} />}>
            Download
          </Button>
          <span className="text-[0.7rem] text-text-muted">coming soon</span>
        </span>
      </div>
      {quant.fit.rationale && (
        <p className="text-[0.75rem] leading-relaxed text-text-muted">{quant.fit.rationale}</p>
      )}
    </div>
  );
}
