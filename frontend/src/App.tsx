import { Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { ObligationDrawerProvider } from "@/contexts/ObligationDrawerContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppShell } from "@/components/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { CalendarPage } from "@/pages/CalendarPage";
import { EntitiesPage } from "@/pages/EntitiesPage";
import { EntityDetailPage } from "@/pages/EntityDetailPage";
import { TasksPage } from "@/pages/TasksPage";
import { RulesPage } from "@/pages/RulesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { AuditLogPage } from "@/pages/AuditLogPage";
import { ObligationDetailPage } from "@/pages/ObligationDetailPage";
import { RegulationLibraryPage } from "@/pages/RegulationLibraryPage";
import { FilingsCatalogPage } from "@/pages/FilingsCatalogPage";
import { LicensesPage } from "@/pages/LicensesPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={150}>
        <AuthProvider>
          <ObligationDrawerProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />

              <Route
                element={
                  <ProtectedRoute>
                    <AppShell />
                  </ProtectedRoute>
                }
              >
                <Route index element={<DashboardPage />} />
                <Route path="calendar" element={<CalendarPage />} />
                <Route path="catalog" element={<FilingsCatalogPage />} />
                <Route path="entities" element={<EntitiesPage />} />
                <Route path="entities/:entityId" element={<EntityDetailPage />} />
                <Route path="tasks" element={<TasksPage />} />
                <Route path="regulations" element={<RegulationLibraryPage />} />
                <Route
                  path="rules"
                  element={
                    <ProtectedRoute requireAdmin>
                      <RulesPage />
                    </ProtectedRoute>
                  }
                />
                <Route path="documents" element={<DocumentsPage />} />
                <Route path="licenses" element={<LicensesPage />} />
                <Route
                  path="audit-log"
                  element={
                    <ProtectedRoute requireAdmin>
                      <AuditLogPage />
                    </ProtectedRoute>
                  }
                />
                <Route path="obligations/:obligationId" element={<ObligationDetailPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </ObligationDrawerProvider>
        </AuthProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
