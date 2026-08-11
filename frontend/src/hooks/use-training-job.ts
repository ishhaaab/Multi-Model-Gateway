import { useEffect, useRef, useState } from "react";
import { trainingApi } from "@/lib/api-endpoints";
import { useTrainingStore } from "@/stores/training-store";
import type { TrainingEvent, TrainingJobDetail, TrainingStatus } from "@/lib/types";

export interface TrainingLiveProgress {
  stage: string;
  progress: number;
  message: string;
}

interface TrainingJobState {
  jobId: string | null;
  detail: TrainingJobDetail | null;
  progress: TrainingLiveProgress | null;
  streaming: boolean;
}

/**
 * Loads a training job's full detail (snapshot via GET), then — if the job was
 * passed in as still active (queued/running) — subscribes to its SSE stream for
 * live progress and the final result. Also feeds status/progress back into the
 * jobs-list store so cards update without a refetch.
 *
 * State only changes in async callbacks (never synchronously in the effect),
 * so a jobId swap immediately renders the loading state and a stale job's
 * events can never overwrite the new job.
 */
export function useTrainingJob(jobId: string | null, initialStatus?: TrainingStatus) {
  const [state, setState] = useState<TrainingJobState>({
    jobId,
    detail: null,
    progress: null,
    streaming: false,
  });
  const patchJob = useTrainingStore((s) => s.patchJob);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    abortRef.current?.abort();
    if (!jobId) return;

    let cancelled = false;
    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      let job: TrainingJobDetail;
      try {
        job = await trainingApi.get(jobId);
      } catch {
        return;
      }
      if (cancelled) return;
      setState((prev) =>
        !cancelled && prev.jobId === jobId
          ? { jobId, detail: job, progress: null, streaming: false }
          : prev
      );

      // Only stream while the job can still move forward; a terminal snapshot
      // (e.g. after a reload) has nothing left to subscribe to.
      const active = initialStatus === "queued" || initialStatus === "running";
      if (!active || (job.status !== "queued" && job.status !== "running")) return;

      setState((prev) =>
        !cancelled && prev.jobId === jobId ? { ...prev, streaming: true } : prev
      );
      try {
        for await (const event of trainingApi.stream(jobId, controller.signal)) {
          if (cancelled) break;
          const ev = event as TrainingEvent;
          if (ev.type === "progress") {
            setState((prev) =>
              !cancelled && prev.jobId === jobId
                ? {
                    ...prev,
                    progress: {
                      stage: ev.stage ?? job.stage ?? "",
                      progress: ev.progress ?? job.progress ?? 0,
                      message: ev.message ?? "",
                    },
                  }
                : prev
            );
            patchJob(jobId, {
              stage: ev.stage ?? null,
              progress: ev.progress ?? 0,
              status: "running",
            });
          } else if (ev.type === "done") {
            if (ev.status === "complete") {
              setState((prev) =>
                !cancelled && prev.jobId === jobId && prev.detail
                  ? {
                      ...prev,
                      detail: {
                        ...prev.detail,
                        status: "complete",
                        progress: 100,
                        artifact_filename: ev.artifact_filename ?? null,
                      },
                    }
                  : prev
              );
              patchJob(jobId, {
                status: "complete",
                progress: 100,
                artifact_filename: ev.artifact_filename ?? null,
              });
            } else {
              setState((prev) =>
                !cancelled && prev.jobId === jobId && prev.detail
                  ? { ...prev, detail: { ...prev.detail, status: "cancelled" } }
                  : prev
              );
              patchJob(jobId, { status: "cancelled" });
            }
          } else if (ev.type === "error") {
            setState((prev) =>
              !cancelled && prev.jobId === jobId && prev.detail
                ? { ...prev, detail: { ...prev.detail, status: "failed", error: ev.message } }
                : prev
            );
            patchJob(jobId, { status: "failed", error: ev.message });
          }
        }
      } catch {
        /* stream closed or aborted */
      } finally {
        if (!cancelled) {
          setState((prev) =>
            !cancelled && prev.jobId === jobId ? { ...prev, streaming: false } : prev
          );
        }
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [jobId, initialStatus, patchJob]);

  if (state.jobId !== jobId) {
    return { detail: null, progress: null, streaming: false };
  }
  return { detail: state.detail, progress: state.progress, streaming: state.streaming };
}
