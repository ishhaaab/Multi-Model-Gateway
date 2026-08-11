import { useEffect, useRef, useState } from "react";
import { trainingApi } from "@/lib/api-endpoints";
import { useTrainingStore } from "@/stores/training-store";
import type { TrainingEvent, TrainingJobDetail, TrainingStatus } from "@/lib/types";

export interface TrainingLiveProgress {
  stage: string;
  progress: number;
  message: string;
}

/**
 * Loads a training job's full detail (snapshot via GET), then — if the job was
 * passed in as still active (queued/running) — subscribes to its SSE stream for
 * live progress and the final result. Also feeds status/progress back into the
 * jobs-list store so cards update without a refetch.
 */
export function useTrainingJob(jobId: string | null, initialStatus?: TrainingStatus) {
  const [detail, setDetail] = useState<TrainingJobDetail | null>(null);
  const [progress, setProgress] = useState<TrainingLiveProgress | null>(null);
  const [streaming, setStreaming] = useState(false);
  const patchJob = useTrainingStore((s) => s.patchJob);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    abortRef.current?.abort();
    if (!jobId) return;

    let cancelled = false;
    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      // Reset to a fresh loading state for this job id.
      setDetail(null);
      setProgress(null);
      setStreaming(false);

      let job: TrainingJobDetail;
      try {
        job = await trainingApi.get(jobId);
      } catch {
        return;
      }
      if (cancelled) return;
      setDetail(job);

      // Only stream while the job can still move forward; a terminal snapshot
      // (e.g. after a reload) has nothing left to subscribe to.
      const active = initialStatus === "queued" || initialStatus === "running";
      if (!active || (job.status !== "queued" && job.status !== "running")) return;

      setStreaming(true);
      try {
        for await (const event of trainingApi.stream(jobId, controller.signal)) {
          if (cancelled) break;
          const ev = event as TrainingEvent;
          if (ev.type === "progress") {
            setProgress({
              stage: ev.stage ?? job.stage ?? "",
              progress: ev.progress ?? job.progress ?? 0,
              message: ev.message ?? "",
            });
            patchJob(jobId, {
              stage: ev.stage ?? null,
              progress: ev.progress ?? 0,
              status: "running",
            });
          } else if (ev.type === "done") {
            if (ev.status === "complete") {
              setDetail((d) =>
                d
                  ? {
                      ...d,
                      status: "complete",
                      progress: 100,
                      artifact_filename: ev.artifact_filename ?? null,
                    }
                  : d
              );
              patchJob(jobId, {
                status: "complete",
                progress: 100,
                artifact_filename: ev.artifact_filename ?? null,
              });
            } else {
              setDetail((d) => (d ? { ...d, status: "cancelled" } : d));
              patchJob(jobId, { status: "cancelled" });
            }
          } else if (ev.type === "error") {
            setDetail((d) => (d ? { ...d, status: "failed", error: ev.message } : d));
            patchJob(jobId, { status: "failed", error: ev.message });
          }
        }
      } catch {
        /* stream closed or aborted */
      } finally {
        if (!cancelled) setStreaming(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [jobId, initialStatus, patchJob]);

  return { detail, progress, streaming };
}
