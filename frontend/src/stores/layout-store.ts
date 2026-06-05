import { create } from "zustand";
import { persist } from "zustand/middleware";

export const SIDEBAR_MIN = 220;
export const SIDEBAR_MAX = 480;

interface LayoutState {
  sidebarWidth: number;
  sidebarCollapsed: boolean;
  setSidebarWidth: (w: number) => void;
  toggleSidebar: () => void;
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      sidebarWidth: 320,
      sidebarCollapsed: false,
      setSidebarWidth: (w) =>
        set({ sidebarWidth: Math.min(Math.max(w, SIDEBAR_MIN), SIDEBAR_MAX) }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    { name: "llm-gateway-layout" }
  )
);
