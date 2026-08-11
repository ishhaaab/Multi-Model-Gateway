import { useState } from "react";
import { Download, X } from "lucide-react";
import { useTrainingStore } from "@/stores/training-store";
import { useTrainingJob } from "@/hooks/use-training-job";
import { trainingApi } from "@/lib/api-endpoints";
import { downloadAuthedFile } from "@/lib/authed-image";
import { toast } from "@/stores/ui-store";
import { ApiError } from "@/lib/api-client";
import type { TrainingStatus } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import AuthedImage from "@/components/images/AuthedImage";

const STATUS_STYLE: Record<TrainingStatus, string> = {
  queued: "text-text-secondary",
  running: "text-accent-secondary",
  complete: "text-success",
  failed: "text-danger",
  cancelled: "text-text-muted",
};

/** One training job: live stream updates, cancel, artifact download, sample. */
export function TrainingCard({ jobId }: { jobId: string }) {
  const job = useTrainingStore((s) => s.jobs.find((j) => j.id === jobId));
  const patchJob = useTrainingStore((s) => s.patchJob);
  const [cancelling, setCancelling] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // While the job is queued/running, subscribe to its SSE stream and patch the
  // store as events arrive.
  const active = job?.status === "queued" || job?.status === "running";
  useTrainingJob(jobId, job?.status);

  if (!job) return null;

  const handleCancel = async () => {
    if (cancelling) return;
    setCancelling(true);
    try {
      await trainingApi.cancel(job.id);
      patchJob(job.id, { status: "cancelled" });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Could not cancel training.");
    } finally {
      setCancelling(false);
    }
  };

  const handleDownload = async () => {
    if (downloading || !job.artifact_filename) return;
    setDownloading(true);
    try {
      await downloadAuthedFile(trainingApi.artifactPath(job.id), job.artifact_filename);
      toast.success("LoRA downloaded.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Could not download LoRA.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-bg-secondary/60 p-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="min-w-0 truncate text-sm font-medium text-text-primary">{job.name}</span>
        <Badge className="ml-auto">{job.base_model}</Badge>
        <Badge className={cn("capitalize", STATUS_STYLE[job.status])}>{job.status}</Badge>
      </div>

      {active && (
        <div className="flex flex-col gap-1.5">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-tertiary">
            <div
              className="h-full rounded-full bg-accent-primary transition-[width] duration-300"
              style={{ width: `${job.progress}%` }}
            />
          </div>
          <span className="flex items-center justify-between gap-3 text-[0.75rem] text-text-muted">
            <span className="truncate">{job.stage || "queued"}</span>
            <span className="shrink-0">{job.progress}%</span>
          </span>
        </div>
      )}

      {job.status === "failed" && job.error && (
        <p className="text-[0.8125rem] text-danger">{job.error}</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-auto text-[0.7rem] text-text-muted">
          {formatRelativeTime(job.created_at)}
        </span>
        {active && (
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<X size={14} />}
            onClick={handleCancel}
            isLoading={cancelling}
          >
            Cancel
          </Button>
        )}
        {job.status === "complete" && job.artifact_filename && (
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Download size={14} />}
            onClick={handleDownload}
            isLoading={downloading}
          >
            Download LoRA
          </Button>
        )}
      </div>

      {job.status === "complete" && job.sample_image && (
        <AuthedImage
          src={trainingApi.samplePath(job.id)}
          alt="Training sample"
          className="mt-2 max-h-40 rounded-md border border-border"
        />
      )}
    </div>
  );
}
