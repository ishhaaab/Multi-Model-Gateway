import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useChatStore } from "@/stores/chat-store";
import { usePresetStore } from "@/stores/preset-store";
import { useTemplateStore } from "@/stores/template-store";

export function AppShell() {
  const fetchConversations = useChatStore((s) => s.fetchConversations);
  const fetchPresets = usePresetStore((s) => s.fetchPresets);
  const fetchTemplates = useTemplateStore((s) => s.fetchTemplates);

  // Warm shared data once after authentication.
  useEffect(() => {
    void fetchConversations();
    void fetchPresets();
    void fetchTemplates();
  }, [fetchConversations, fetchPresets, fetchTemplates]);

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
