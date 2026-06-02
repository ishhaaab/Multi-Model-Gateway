import { create } from "zustand";
import { persist } from "zustand/middleware";
import { authApi } from "@/lib/api-endpoints";

interface AuthState {
  isAuthenticated: boolean;
  accessToken: string | null;
  refreshToken: string | null;
  userEmail: string | null;
  isInitializing: boolean;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  forceLogout: () => void;
  setAccessToken: (token: string) => void;
  initializeAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      isAuthenticated: false,
      accessToken: null,
      refreshToken: null,
      userEmail: null,
      isInitializing: true,

      login: async (email, password) => {
        const res = await authApi.login(email, password);
        set({
          isAuthenticated: true,
          accessToken: res.access_token,
          refreshToken: res.refresh_token,
          userEmail: email,
        });
      },

      register: async (email, password) => {
        await authApi.register(email, password);
      },

      logout: async () => {
        const { refreshToken } = get();
        if (refreshToken) {
          try {
            await authApi.logout(refreshToken);
          } catch {
            /* best-effort: clear locally regardless */
          }
        }
        set({
          isAuthenticated: false,
          accessToken: null,
          refreshToken: null,
          userEmail: null,
        });
      },

      // Synchronous local clear — used when a token refresh fails mid-request.
      forceLogout: () => {
        set({
          isAuthenticated: false,
          accessToken: null,
          refreshToken: null,
          userEmail: null,
        });
      },

      setAccessToken: (token) => set({ accessToken: token }),

      initializeAuth: async () => {
        const { refreshToken } = get();
        if (!refreshToken) {
          set({ isInitializing: false, isAuthenticated: false });
          return;
        }
        try {
          const res = await authApi.refresh(refreshToken);
          set({
            isAuthenticated: true,
            accessToken: res.access_token,
            isInitializing: false,
          });
        } catch {
          set({
            isAuthenticated: false,
            accessToken: null,
            refreshToken: null,
            isInitializing: false,
          });
        }
      },
    }),
    {
      name: "llm-gateway-auth",
      partialize: (state) => ({
        refreshToken: state.refreshToken,
        userEmail: state.userEmail,
      }),
    }
  )
);
