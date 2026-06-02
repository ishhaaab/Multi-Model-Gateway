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
} from "lucide-react";
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

  const handleNewChat = () => {
    startNewChat();
    navigate("/chat");
  };

  const handleLogout = async () => {
    await logout();
    toast.info("Signed out.");
    navigate("/login");
  };

  return (
    <aside className="flex h-full w-[320px] shrink-0 flex-col border-r border-border bg-bg-secondary/80">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-bg-tertiary">
          <Brain size={18} className="text-accent-primary" />
        </span>
        <span className="font-serif text-[1.35rem] leading-none text-text-primary">
          llm-gateway
        </span>
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
    </aside>
  );
}
