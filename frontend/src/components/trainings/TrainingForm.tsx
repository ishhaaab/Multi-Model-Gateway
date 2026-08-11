import { useState } from "react";
import { Upload } from "lucide-react";
import { useTrainingStore } from "@/stores/training-store";
import { toast } from "@/stores/ui-store";
import { ApiError } from "@/lib/api-client";
import type { TrainingBaseModel } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Dropdown } from "@/components/ui/Dropdown";
import type { DropdownOption } from "@/components/ui/Dropdown";

const BASE_MODEL_OPTIONS: DropdownOption[] = [
  { value: "flux-dev", label: "FLUX.1-dev" },
  { value: "sdxl", label: "SDXL" },
  { value: "sd1", label: "SD1" },
];

interface TrainingFormProps {
  /** Called with the created job id so the page can scroll/highlight it. */
  onCreated?: (jobId: string) => void;
}

/**
 * LoRA training form — name, base model, dataset zip, steps, learning rate,
 * resolution. Submits a multipart form to POST /v1/trainings.
 */
export function TrainingForm({ onCreated }: TrainingFormProps) {
  const createJob = useTrainingStore((s) => s.createJob);

  const [name, setName] = useState("");
  const [baseModel, setBaseModel] = useState<TrainingBaseModel>("flux-dev");
  const [dataset, setDataset] = useState<File | null>(null);
  const [steps, setSteps] = useState("1000");
  const [learningRate, setLearningRate] = useState("0.0001");
  const [resolution, setResolution] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!name.trim()) {
      toast.error("Training name is required.");
      return;
    }
    if (!dataset) {
      toast.error("Choose a dataset zip first.");
      return;
    }
    if (!dataset.name.toLowerCase().endsWith(".zip")) {
      toast.error("Dataset must be a .zip file.");
      return;
    }
    const stepsNum = Number(steps);
    if (!Number.isFinite(stepsNum) || stepsNum < 100 || stepsNum > 20000) {
      toast.error("Steps must be between 100 and 20000.");
      return;
    }
    const lrNum = Number(learningRate);
    if (!Number.isFinite(lrNum) || lrNum <= 0) {
      toast.error("Learning rate must be greater than 0.");
      return;
    }
    const resNum = resolution.trim() ? Number(resolution) : undefined;
    if (resNum !== undefined && (!Number.isFinite(resNum) || resNum < 256 || resNum > 2048)) {
      toast.error("Resolution must be between 256 and 2048.");
      return;
    }

    setSaving(true);
    try {
      const jobId = await createJob({
        name: name.trim(),
        base_model: baseModel,
        dataset,
        steps: stepsNum,
        learning_rate: lrNum,
        ...(resNum !== undefined ? { resolution: resNum } : {}),
      });
      toast.success("Training started.");
      // Clear the form but keep the base model — most users train the same
      // family back-to-back.
      setName("");
      setDataset(null);
      setSteps("1000");
      setLearningRate("0.0001");
      setResolution("");
      onCreated?.(jobId);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Could not start training.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. my-flux-style"
          containerClassName="sm:col-span-2"
        />

        <div className="flex flex-col gap-1.5">
          <label className="text-[0.8125rem] font-medium text-text-secondary">Base model</label>
          <Dropdown
            value={baseModel}
            options={BASE_MODEL_OPTIONS}
            onChange={(v) => setBaseModel(v as TrainingBaseModel)}
            className="w-full"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-[0.8125rem] font-medium text-text-secondary">Dataset (.zip)</label>
          <label
            className={cn(
              "flex h-10 cursor-pointer items-center justify-between gap-2 rounded-lg border border-dashed px-3 text-sm transition-colors",
              dataset
                ? "border-accent-primary/50 bg-bg-secondary text-text-primary"
                : "border-border bg-bg-secondary text-text-muted hover:bg-bg-tertiary"
            )}
          >
            <span className="flex min-w-0 items-center gap-2">
              <Upload size={15} className="shrink-0 text-text-muted" />
              <span className="truncate">{dataset ? dataset.name : "Choose a zip of images…"}</span>
            </span>
            <input
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => setDataset(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:col-span-2 sm:grid-cols-3">
          <Input
            label="Steps"
            type="number"
            value={steps}
            onChange={(e) => setSteps(e.target.value)}
            min={100}
            max={20000}
          />
          <Input
            label="Learning rate"
            type="number"
            value={learningRate}
            onChange={(e) => setLearningRate(e.target.value)}
            step={0.0001}
            min={0}
          />
          <Input
            label="Resolution"
            type="number"
            value={resolution}
            onChange={(e) => setResolution(e.target.value)}
            placeholder="Auto"
            min={256}
            max={2048}
            hint="Blank = 512 for SD1, 1024 otherwise"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="primary" onClick={save} isLoading={saving}>
          Start Training
        </Button>
      </div>
    </div>
  );
}
