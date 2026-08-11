import { useEffect } from "react";
import { RotateCw } from "lucide-react";
import { useTrainingStore } from "@/stores/training-store";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { TrainingForm } from "@/components/trainings/TrainingForm";
import { TrainingCard } from "@/components/trainings/TrainingCard";

export default function TrainingsPage() {
  const { jobs, isLoading, hasLoaded, fetchJobs } = useTrainingStore();

  useEffect(() => {
    if (!hasLoaded) void fetchJobs();
  }, [hasLoaded, fetchJobs]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-border px-6 py-4 max-md:pl-14">
        <div>
          <h1 className="text-2xl text-text-primary">LoRA Training</h1>
          <p className="text-sm text-text-secondary">Fine-tune an image LoRA from your dataset</p>
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-6">
          <section className="rounded-lg border border-border bg-bg-secondary/40 p-4">
            <h2 className="mb-4 text-sm font-medium text-text-secondary">New training</h2>
            <TrainingForm />
          </section>

          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-medium text-text-secondary">Recent trainings</h2>
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<RotateCw size={14} />}
                onClick={() => void fetchJobs()}
                disabled={isLoading}
              >
                Refresh
              </Button>
            </div>

            {isLoading && jobs.length === 0 ? (
              <div className="flex flex-col gap-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-24 w-full" />
                ))}
              </div>
            ) : jobs.length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-text-muted">
                No trainings yet. Start one above.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {jobs.map((j) => (
                  <TrainingCard key={j.id} jobId={j.id} />
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
