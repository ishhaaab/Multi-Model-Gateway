import { useRef, type MouseEvent as ReactMouseEvent } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Brain,
  MessageSquarePlus,
  ImageIcon,
  SlidersHorizontal,
  LayoutTemplate,
  Settings,
  LogOut,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useLayoutStore, SIDEBAR_MIN, SIDEBAR_MAX } from "@/stores/layout-store";
import { useAuthStore } from "@/stores/auth-store";
import { useChatStore } from "@/stores/chat-store";
import { toast } from "@/stores/ui-store";
import { cn } from "@/lib/utils";
import { ConversationList } from "@/components/chat/ConversationList";

const NAV = [
  { to: "/chat", label: "Chat", icon: MessagesSquare },
  { to: "/images", label: "Images", icon: ImageIcon },
  { to: "/presets", label: "Presets", icon: SlidersHorizontal },
  { to: "/templates", label: "Templates", icon: LayoutTemplate },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const navigate = useNavigate();
  const userEmail = useAuthStore((s) => s.userEmail);
  const logout = useAuthStore((s) => s.logout);
  const startNewChat = useChatStore((s) => s.startNewChat);

  const sidebarWidth = useLayoutStore((s) => s.sidebarWidth);
  const setSidebarWidth = useLayoutStore((s) => s.setSidebarWidth);
  const toggleSidebar = useLayoutStore((s) => s.toggleSidebar);
  const collapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const asideRef = useRef<HTMLElement>(null);

  // Live-resize via direct style writes during drag; commit once on mouse-up.
  const startResize = (e: ReactMouseEvent) => {
    e.preventDefault();
    let w = sidebarWidth;
    const onMove = (ev: MouseEvent) => {
      w = Math.min(Math.max(ev.clientX, SIDEBAR_MIN), SIDEBAR_MAX);
      if (asideRef.current) asideRef.current.style.width = `${w}px`;
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setSidebarWidth(w);
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const handleNewChat = () => {
    startNewChat();
    navigate("/chat");
  };

  const handleLogout = async () => {
    await logout();
    toast.info("Signed out.");
    navigate("/login");
  };

  // Collapsed → a slim icon rail that mirrors the expanded layout's vertical
  // positions (new chat at top, nav at the bottom, user in the footer).
  if (collapsed) {
    return (
      <aside className="flex h-full w-14 shrink-0 flex-col border-r border-border bg-bg-secondary/80">
        {/* top: expand (in place of the logo) + new chat */}
        <div className="flex flex-col items-center gap-2 px-2 pt-5 pb-3">
          <button
            onClick={toggleSidebar}
            title="Expand sidebar"
            aria-label="Expand sidebar"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-bg-tertiary hover:text-text-primary"
          >
            <PanelLeftOpen size={20} />
          </button>
          <button
            onClick={handleNewChat}
            title="New Chat"
            aria-label="New Chat"
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-primary text-white transition-[filter] hover:brightness-110"
          >
            <MessageSquarePlus size={18} />
          </button>
        </div>

        {/* spacer where the conversation list sits when expanded */}
        <div className="min-h-0 flex-1" />

        {/* nav icons — at the bottom, same as the expanded layout */}
        <nav className="flex flex-col items-center gap-1 border-t border-border px-2 py-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              title={label}
              className={({ isActive }) =>
                cn(
                  "flex h-9 w-9 items-center justify-center rounded-lg transition-colors",
                  isActive
                    ? "bg-bg-tertiary text-accent-primary"
                    : "text-text-secondary hover:bg-bg-tertiary/60 hover:text-text-primary"
                )
              }
            >
              <Icon size={18} />
            </NavLink>
          ))}
        </nav>

        {/* user — footer */}
        <div className="flex justify-center border-t border-border px-2 py-3">
          <button
            onClick={toggleSidebar}
            title={userEmail ?? "Account"}
            aria-label="Account"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-bg-elevated text-[0.7rem] font-semibold uppercase text-text-primary transition-colors hover:bg-bg-tertiary"
          >
            {userEmail?.[0] ?? "?"}
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside
      ref={asideRef}
      style={{ width: sidebarWidth }}
      className="relative flex h-full shrink-0 flex-col border-r border-border bg-bg-secondary/80"
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-bg-tertiary">
          <Brain size={18} className="text-accent-primary" />
        </span>
        <span className="font-serif text-[1.35rem] leading-none text-text-primary">
          llm-gateway
        </span>
        <button
          onClick={toggleSidebar}
          className="ml-auto flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-bg-tertiary hover:text-text-primary"
          title="Collapse sidebar"
          aria-label="Collapse sidebar"
        >
          <PanelLeftClose size={17} />
        </button>
      </div>

      {/* New chat */}
      <div className="px-3 pb-3">
        <button
          onClick={handleNewChat}
          className={cn(
            "flex w-full items-center justify-center gap-2 rounded-lg bg-accent-primary px-4 py-2.5",
            "text-sm font-medium text-white transition-[transform,filter] duration-150",
            "hover:brightness-110 active:scale-[0.98] shadow-[0_2px_12px_-2px_rgba(255,101,63,0.5)]"
          )}
        >
          <MessageSquarePlus size={17} />
          New Chat
        </button>
      </div>

      {/* Conversations */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        <ConversationList />
      </div>

      {/* Nav links */}
      <nav className="border-t border-border px-2 py-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-bg-tertiary text-text-primary"
                  : "text-text-secondary hover:bg-bg-tertiary/60 hover:text-text-primary"
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={17}
                  className={isActive ? "text-accent-primary" : undefined}
                />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer / user */}
      <div className="flex items-center justify-between gap-2 border-t border-border px-3 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-bg-elevated text-[0.7rem] font-semibold uppercase text-text-primary">
            {userEmail?.[0] ?? "?"}
          </span>
          <span className="truncate text-[0.8125rem] text-text-secondary" title={userEmail ?? undefined}>
            {userEmail ?? "Unknown"}
          </span>
        </div>
        <button
          onClick={handleLogout}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-text-muted hover:bg-bg-tertiary hover:text-danger transition-colors"
          aria-label="Log out"
          title="Log out"
        >
          <LogOut size={16} />
        </button>
      </div>

      {/* Drag-to-resize handle on the border shared with the main area */}
      <div
        onMouseDown={startResize}
        className="absolute right-0 top-0 z-20 h-full w-1.5 cursor-col-resize transition-colors hover:bg-accent-primary/40 active:bg-accent-primary/60"
        title="Drag to resize"
      />
    </aside>
  );
}
