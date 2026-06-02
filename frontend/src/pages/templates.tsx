import { useEffect, useMemo, useState } from "react";
import { Plus, Star, LayoutTemplate, Trash2, Wand2 } from "lucide-react";
import { useTemplateStore } from "@/stores/template-store";
import { templateApi } from "@/lib/api-endpoints";
import { toast } from "@/stores/ui-store";
import { ApiError } from "@/lib/api-client";
import type { PromptTemplate } from "@/lib/types";
import { cn, truncate } from "@/lib/utils";
import { TwoPanel } from "@/components/layout/TwoPanel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Spinner } from "@/components/ui/Spinner";

interface FormState {
  name: string;
  description: string;
  structure: string;
}

const DEFAULT_STRUCTURE = `quality,
art style, artist references,
camera,
subject,
accessories and clothes,
pose,
environment,
lighting`;

const NEW_FORM: FormState = { name: "", description: "", structure: DEFAULT_STRUCTURE };

export default function TemplatesPage() {
  const {
    templates,
    isLoading,
    hasLoaded,
    fetchTemplates,
    createTemplate,
    updateTemplate,
    deleteTemplate,
  } = useTemplateStore();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<FormState>(NEW_FORM);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Test rewrite
  const [testPrompt, setTestPrompt] = useState("a cat wearing a hat");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!hasLoaded) void fetchTemplates();
  }, [hasLoaded, fetchTemplates]);

  const selected = useMemo(
    () => templates.find((t) => t.id === selectedId) ?? null,
    [templates, selectedId]
  );

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const selectTemplate = (t: PromptTemplate) => {
    setCreating(false);
    setSelectedId(t.id);
    setForm({ name: t.name, description: t.description ?? "", structure: t.structure });
    setTestResult(null);
  };

  const startCreate = () => {
    setCreating(true);
    setSelectedId(null);
    setForm(NEW_FORM);
    setTestResult(null);
  };

  const save = async () => {
    if (!form.name.trim()) {
      toast.error("Template name is required.");
      return;
    }
    if (!form.structure.trim()) {
      toast.error("Structure is required.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim(),
        structure: form.structure,
      };
      if (creating) {
        const created = await createTemplate(payload);
        toast.success("Template created.");
        setCreating(false);
        setSelectedId(created.id);
      } else if (selectedId) {
        await updateTemplate(selectedId, payload);
        toast.success("Template saved.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Could not save template.");
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async () => {
    if (!selectedId) return;
    setDeleting(true);
    try {
      await deleteTemplate(selectedId);
      toast.success("Template deleted.");
      setSelectedId(null);
      setForm(NEW_FORM);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Could not delete template.");
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const runTest = async () => {
    if (!testPrompt.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      // Saved template → use its id; unsaved/new → fall back to default structure.
      const { rewritten_prompt } = await templateApi.rewrite(
        testPrompt.trim(),
        selected ? selected.id : null
      );
      setTestResult(rewritten_prompt);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Rewrite failed.");
    } finally {
      setTesting(false);
    }
  };

  const editing = creating || !!selected;

  const list = (
    <div className="flex flex-col gap-2">
      <Button variant="primary" fullWidth leftIcon={<Plus size={16} />} onClick={startCreate}>
        Create New Template
      </Button>

      {isLoading && templates.length === 0 ? (
        <div className="flex flex-col gap-2 pt-1">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : templates.length === 0 ? (
        <p className="px-2 py-6 text-center text-sm text-text-muted">No templates yet.</p>
      ) : (
        templates.map((t) => {
          const isDefault = t.name === "Default SDXL Template";
          const active = t.id === selectedId && !creating;
          return (
            <button
              key={t.id}
              onClick={() => selectTemplate(t)}
              className={cn(
                "flex flex-col gap-1 rounded-lg border-l-2 px-3 py-2.5 text-left transition-colors",
                active
                  ? "border-accent-primary bg-bg-tertiary"
                  : "border-transparent hover:bg-bg-tertiary/60"
              )}
            >
              <span className="flex items-center gap-1.5">
                {isDefault && <Star size={13} className="text-accent-secondary" fill="currentColor" />}
                <span className="truncate text-sm font-medium text-text-primary">{t.name}</span>
              </span>
              {t.description && (
                <span className="truncate text-[0.75rem] text-text-muted">
                  {truncate(t.description, 60)}
                </span>
              )}
            </button>
          );
        })
      )}
    </div>
  );

  const detail = !editing ? (
    <EmptyState
      icon={<LayoutTemplate size={40} strokeWidth={1.5} />}
      title="No template selected"
      description="Select a template to edit, or create one to customize how prompts are rewritten for image generation."
      action={
        <Button variant="primary" leftIcon={<Plus size={16} />} onClick={startCreate}>
          Create Template
        </Button>
      }
    />
  ) : (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 animate-fade-in">
      <Input
        label="Template Name"
        value={form.name}
        onChange={(e) => set("name", e.target.value)}
        placeholder="e.g. Portrait Template"
      />
      <Input
        label="Description"
        value={form.description}
        onChange={(e) => set("description", e.target.value)}
        placeholder="What is this template for?"
      />
      <Textarea
        label="Structure (one category per line)"
        mono
        value={form.structure}
        onChange={(e) => set("structure", e.target.value)}
        className="min-h-[250px]"
        hint="Each line is a category the AI fills in, passed verbatim to the rewriter."
      />

      {/* Test rewrite */}
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-bg-secondary/60 p-4">
        <div className="flex items-center gap-2">
          <Wand2 size={16} className="text-accent-secondary" />
          <h3 className="font-sans text-sm font-medium text-text-primary">Test Rewrite</h3>
        </div>
        <Textarea
          value={testPrompt}
          onChange={(e) => setTestPrompt(e.target.value)}
          placeholder="Enter a test prompt…"
          className="min-h-[60px]"
        />
        <div>
          <Button variant="secondary" onClick={runTest} isLoading={testing} leftIcon={<Wand2 size={15} />}>
            {testing ? "Rewriting…" : "Test Rewrite"}
          </Button>
          {!selected && creating && (
            <p className="mt-1.5 text-[0.75rem] text-text-muted">
              Save the template first to test its structure — until then the default structure is used.
            </p>
          )}
        </div>
        {testing && (
          <div className="flex items-center gap-2 text-[0.8125rem] text-text-muted">
            <Spinner size={14} /> The rewriter model loads on demand (~10–20s)…
          </div>
        )}
        {testResult && (
          <div className="rounded-lg border border-border bg-bg-primary p-3">
            <p className="font-mono text-[0.8125rem] leading-relaxed text-text-primary">
              {testResult}
            </p>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-border pt-4">
        <Button variant="primary" onClick={save} isLoading={saving}>
          {creating ? "Create Template" : "Save"}
        </Button>
        {selected && (
          <Button variant="danger" leftIcon={<Trash2 size={15} />} onClick={() => setConfirmDelete(true)}>
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
      <TwoPanel
        title="Prompt Templates"
        subtitle="SDXL prompt rewriting structures"
        list={list}
        detail={detail}
      />
      <ConfirmDialog
        open={confirmDelete}
        title="Delete template"
        message="Are you sure? This cannot be undone."
        confirmLabel="Delete Template"
        isLoading={deleting}
        onConfirm={doDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
