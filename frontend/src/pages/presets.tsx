import { useEffect, useMemo, useState } from "react";
import { Plus, Star, SlidersHorizontal, Trash2 } from "lucide-react";
import { usePresetStore } from "@/stores/preset-store";
import { toast } from "@/stores/ui-store";
import { ApiError } from "@/lib/api-client";
import type { Preset, PresetCreate } from "@/lib/types";
import { cn, truncate } from "@/lib/utils";
import { TwoPanel } from "@/components/layout/TwoPanel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Slider } from "@/components/ui/Slider";
import { Dropdown } from "@/components/ui/Dropdown";
import { StopStrings } from "@/components/ui/StopStrings";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface FormState {
  name: string;
  system_prompt: string;
  temperature: number;
  top_p: number;
  top_k: number;
  min_p: number;
  repeat_penalty: number;
  token_limit: string; // empty = unlimited
  context_overflow: string;
  stop_strings: string[];
}

const NEW_FORM: FormState = {
  name: "",
  system_prompt: "",
  temperature: 0.8,
  top_p: 0.95,
  top_k: 40,
  min_p: 0.05,
  repeat_penalty: 1.1,
  token_limit: "",
  context_overflow: "truncate_middle",
  stop_strings: [],
};

function presetToForm(p: Preset): FormState {
  return {
    name: p.name,
    system_prompt: p.system_prompt ?? "",
    temperature: p.temperature ?? 0.8,
    top_p: p.top_p ?? 0.95,
    top_k: p.top_k ?? 40,
    min_p: p.min_p ?? 0.05,
    repeat_penalty: p.repeat_penalty ?? 1.1,
    token_limit: p.token_limit != null ? String(p.token_limit) : "",
    context_overflow: p.context_overflow ?? "truncate_middle",
    stop_strings: p.stop_strings ?? [],
  };
}

export default function PresetsPage() {
  const { presets, isLoading, hasLoaded, fetchPresets, createPreset, updatePreset, deletePreset } =
    usePresetStore();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<FormState>(NEW_FORM);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!hasLoaded) void fetchPresets();
  }, [hasLoaded, fetchPresets]);

  const selected = useMemo(
    () => presets.find((p) => p.id === selectedId) ?? null,
    [presets, selectedId]
  );

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const selectPreset = (p: Preset) => {
    setCreating(false);
    setSelectedId(p.id);
    setForm(presetToForm(p));
  };

  const startCreate = () => {
    setCreating(true);
    setSelectedId(null);
    setForm(NEW_FORM);
  };

  const buildPayload = (): PresetCreate => ({
    name: form.name.trim(),
    system_prompt: form.system_prompt.trim() || null,
    temperature: form.temperature,
    top_p: form.top_p,
    top_k: form.top_k,
    min_p: form.min_p,
    repeat_penalty: form.repeat_penalty,
    token_limit: form.token_limit.trim() ? Number(form.token_limit) : null,
    context_overflow: form.context_overflow,
    stop_strings: form.stop_strings.length ? form.stop_strings : null,
  });

  const save = async () => {
    if (!form.name.trim()) {
      toast.error("Preset name is required.");
      return;
    }
    setSaving(true);
    try {
      if (creating) {
        const created = await createPreset(buildPayload());
        toast.success("Preset created.");
        setCreating(false);
        setSelectedId(created.id);
      } else if (selectedId) {
        await updatePreset(selectedId, buildPayload());
        toast.success("Preset saved.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Could not save preset.");
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async () => {
    if (!selectedId) return;
    setDeleting(true);
    try {
      await deletePreset(selectedId);
      toast.success("Preset deleted.");
      setSelectedId(null);
      setForm(NEW_FORM);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Could not delete preset.");
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const editing = creating || !!selected;

  // ---- list panel ----
  const list = (
    <div className="flex flex-col gap-2">
      <Button variant="primary" fullWidth leftIcon={<Plus size={16} />} onClick={startCreate}>
        Create New Preset
      </Button>

      {isLoading && presets.length === 0 ? (
        <div className="flex flex-col gap-2 pt-1">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : presets.length === 0 ? (
        <p className="px-2 py-6 text-center text-sm text-text-muted">No presets yet.</p>
      ) : (
        presets.map((p) => {
          const isDefault = p.name === "Default";
          const active = p.id === selectedId && !creating;
          return (
            <button
              key={p.id}
              onClick={() => selectPreset(p)}
              className={cn(
                "flex flex-col gap-1 rounded-lg border-l-2 px-3 py-2.5 text-left transition-colors",
                active
                  ? "border-accent-primary bg-bg-tertiary"
                  : "border-transparent hover:bg-bg-tertiary/60"
              )}
            >
              <span className="flex items-center gap-1.5">
                {isDefault && <Star size={13} className="text-accent-secondary" fill="currentColor" />}
                <span className="truncate text-sm font-medium text-text-primary">{p.name}</span>
                <span className="ml-auto rounded bg-bg-elevated/60 px-1.5 py-0.5 font-mono text-[0.7rem] text-text-secondary">
                  temp {p.temperature}
                </span>
              </span>
              {p.system_prompt && (
                <span className="truncate text-[0.75rem] text-text-muted">
                  {truncate(p.system_prompt, 50)}
                </span>
              )}
            </button>
          );
        })
      )}
    </div>
  );

  // ---- detail panel ----
  const detail = !editing ? (
    <EmptyState
      icon={<SlidersHorizontal size={40} strokeWidth={1.5} />}
      title="No preset selected"
      description="Select a preset to edit, or create a new one to customize your AI's behavior."
      action={
        <Button variant="primary" leftIcon={<Plus size={16} />} onClick={startCreate}>
          Create Preset
        </Button>
      }
    />
  ) : (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 animate-fade-in">
      <Input
        label="Preset Name"
        value={form.name}
        onChange={(e) => set("name", e.target.value)}
        placeholder="e.g. Creative Writing"
      />

      <Textarea
        label="System Prompt"
        mono
        value={form.system_prompt}
        onChange={(e) => set("system_prompt", e.target.value)}
        placeholder="Instructions that set the AI's behavior…"
        className="min-h-[150px]"
      />

      <Slider
        label="Temperature"
        value={form.temperature}
        min={0}
        max={2}
        step={0.1}
        onChange={(v) => set("temperature", v)}
        endLabels={["Precise (0.0)", "Creative (2.0)"]}
      />

      <Slider
        label="Top P"
        value={form.top_p}
        min={0}
        max={1}
        step={0.01}
        onChange={(v) => set("top_p", v)}
      />

      <Input
        label="Top K"
        type="number"
        min={1}
        max={100}
        value={form.top_k}
        onChange={(e) => set("top_k", Number(e.target.value))}
        hint="Limit sampling to the top K tokens"
      />

      <Slider
        label="Min P"
        value={form.min_p}
        min={0}
        max={1}
        step={0.01}
        onChange={(v) => set("min_p", v)}
        hint="Minimum probability threshold"
      />

      <Slider
        label="Repeat Penalty"
        value={form.repeat_penalty}
        min={0}
        max={2}
        step={0.01}
        onChange={(v) => set("repeat_penalty", v)}
        hint="Higher values reduce repetition"
      />

      <Input
        label="Max Tokens"
        type="number"
        min={1}
        value={form.token_limit}
        onChange={(e) => set("token_limit", e.target.value)}
        placeholder="∞"
        hint="Leave empty for unlimited"
      />

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-text-secondary">Context Overflow</label>
        <Dropdown
          value={form.context_overflow}
          options={[{ value: "truncate_middle", label: "truncate_middle" }]}
          onChange={(v) => set("context_overflow", v)}
          className="w-full max-w-xs"
        />
      </div>

      <StopStrings value={form.stop_strings} onChange={(v) => set("stop_strings", v)} />

      <div className="flex items-center gap-2 border-t border-border pt-4">
        <Button variant="primary" onClick={save} isLoading={saving}>
          {creating ? "Create Preset" : "Save"}
        </Button>
        {selected && (
          <Button
            variant="danger"
            leftIcon={<Trash2 size={15} />}
            onClick={() => setConfirmDelete(true)}
          >
            Delete
          </Button>
        )}
        <Button
          variant="ghost"
          onClick={() => {
            setCreating(false);
            setSelectedId(null);
          }}
        >
          Cancel
        </Button>
      </div>
    </div>
  );

  return (
    <>
      <TwoPanel title="Presets" subtitle="Saved model parameter profiles" list={list} detail={detail} />
      <ConfirmDialog
        open={confirmDelete}
        title="Delete preset"
        message="Are you sure? This cannot be undone."
        confirmLabel="Delete Preset"
        isLoading={deleting}
        onConfirm={doDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
