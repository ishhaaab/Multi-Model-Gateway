import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth-store";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";
import { Toaster } from "@/components/ui/Toaster";

import LoginPage from "@/pages/login";
import RegisterPage from "@/pages/register";
import ChatPage from "@/pages/chat";
import ImagesPage from "@/pages/images";
import PresetsPage from "@/pages/presets";
import TemplatesPage from "@/pages/templates";
import WorkflowsPage from "@/pages/workflows";
import SettingsPage from "@/pages/settings";
import NotFoundPage from "@/pages/not-found";

export default function App() {
  const initializeAuth = useAuthStore((s) => s.initializeAuth);

  // Restore the session silently on load (refresh-token → fresh access token).
  useEffect(() => {
    void initializeAuth();
  }, [initializeAuth]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:id" element={<ChatPage />} />
          <Route path="/images" element={<ImagesPage />} />
          <Route path="/presets" element={<PresetsPage />} />
          <Route path="/templates" element={<TemplatesPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <Toaster />
    </BrowserRouter>
  );
}
