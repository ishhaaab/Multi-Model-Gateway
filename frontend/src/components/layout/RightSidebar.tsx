import { useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { useLocation } from "react-router-dom";
import {
  SlidersHorizontal,
  LayoutTemplate,
  Workflow as WorkflowIcon,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";
import {
  useLayoutStore,
  RIGHT_SIDEBAR_MIN,
  RIGHT_SIDEBAR_MAX,
} from "@/stores/layout-store";
import { cn } from "@/lib/utils";
import { PresetPanel } from "@/components/settings/PresetPanel";
import { TemplatePanel } from "@/components/settings/TemplatePanel";
import { WorkflowPanel } from "@/components/settings/WorkflowPanel";

type Kind = "chat" | "images";
type ImageTab = "templates" | "workflows";

/** Which contextual panel (if any) belongs to the current route. */
function kindForPath(pathname: string): Kind | null {
  if (pathname.startsWith("/images")) return "images";
  if (pathname.startsWith("/chat")) return "chat";
  return null;
}

const IMAGE_TABS = [
  { id: "workflows" as const, label: "Workflows", icon: WorkflowIcon },
  { id: "templates" as const, label: "Templates", icon: LayoutTemplate },
];

export function RightSidebar() {
  const { pathname } = useLocation();
  const kind = kindForPath(pathname);

  const width = useLayoutStore((s) => s.rightSidebarWidth);
  const setWidth = useLayoutStore((s) => s.setRightSidebarWidth);
  const collapsed = useLayoutStore((s) => s.rightSidebarCollapsed);
  const toggle = useLayoutStore((s) => s.toggleRightSidebar);
  const asideRef = useRef<HTMLElement>(null);
  const [imageTab, setImageTab] = useState<ImageTab>("workflows");

  // The panel only exists for chat/image routes (settings etc. have none).
  if (!kind) return null;

  // Collapsed rail mirrors the currently-selected image tab (workflows/templates).
  const activeImageTab = IMAGE_TABS.find((t) => t.id === imageTab) ?? IMAGE_TABS[0];
  const railIcon = kind === "chat" ? SlidersHorizontal : activeImageTab.icon;
  const railLabel = kind === "chat" ? "Presets" : activeImageTab.label;

  // Live-resize via direct style writes during drag; commit once on mouse-up.
  // The aside is flush to the viewport's right edge, so width = innerWidth − x.
  const startResize = (e: ReactMouseEvent) => {
    e.preventDefault();
    let w = width;
    const onMove = (ev: MouseEvent) => {
      w = Math.min(
        Math.max(window.innerWidth - ev.clientX, RIGHT_SIDEBAR_MIN),
        RIGHT_SIDEBAR_MAX
      );
      if (asideRef.current) asideRef.current.style.width = `${w}px`;
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setWidth(w);
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  // Collapsed → a slim icon rail that expands on click.
  if (collapsed) {
    const RailIcon = railIcon;
    return (
      <aside className="flex h-full w-14 shrink-0 flex-col items-center border-l border-border bg-bg-secondary/80 px-2 pt-5">
        <button
          onClick={toggle}
          title={`Show ${railLabel.toLowerCase()}`}
          aria-label={`Show ${railLabel.toLowerCase()}`}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-bg-tertiary hover:text-text-primary"
        >
          <PanelRightOpen size={20} />
        </button>
        <button
          onClick={toggle}
          title={railLabel}
          aria-label={railLabel}
          className="mt-2 flex h-9 w-9 items-center justify-center rounded-lg text-accent-primary transition-colors hover:bg-bg-tertiary"
        >
          <RailIcon size={18} />
        </button>
      </aside>
    );
  }

  return (
    <aside
      ref={asideRef}
      style={{ width }}
      className="relative flex h-full shrink-0 flex-col border-l border-border bg-bg-secondary/80"
    >
      {/* Header — a title for chat, a Templates|Workflows toggle for images */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        {kind === "chat" ? (
          <>
            <SlidersHorizontal size={16} className="shrink-0 text-accent-primary" />
            <span className="font-serif text-[1.15rem] leading-none text-text-primary">Presets</span>
          </>
        ) : (
          <div className="flex gap-1 rounded-lg border border-border bg-bg-primary/40 p-0.5">
            {IMAGE_TABS.map(({ id, label, icon: TabIcon }) => (
              <button
                key={id}
                onClick={() => setImageTab(id)}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[0.8125rem] font-medium transition-colors",
                  imageTab === id
                    ? "bg-bg-elevated text-text-primary shadow-[0_1px_3px_rgba(0,0,0,0.35)]"
                    : "text-text-secondary hover:text-text-primary"
                )}
              >
                <TabIcon size={13} className={imageTab === id ? "text-accent-primary" : undefined} />
                {label}
              </button>
            ))}
          </div>
        )}
        <button
          onClick={toggle}
          className="ml-auto flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-bg-tertiary hover:text-text-primary"
          title="Collapse panel"
          aria-label="Collapse panel"
        >
          <PanelRightClose size={17} />
        </button>
      </div>

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {kind === "chat" ? (
          <PresetPanel />
        ) : imageTab === "templates" ? (
          <TemplatePanel />
        ) : (
          <WorkflowPanel />
        )}
      </div>

      {/* Drag-to-resize handle on the border shared with the main area */}
      <div
        onMouseDown={startResize}
        className="absolute left-0 top-0 z-20 h-full w-1.5 cursor-col-resize transition-colors hover:bg-accent-primary/40 active:bg-accent-primary/60"
        title="Drag to resize"
      />
    </aside>
  );
}
