import { Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { ObligationDrawerProvider } from "@/contexts/ObligationDrawerContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppShell } from "@/components/AppShell";
import { WorkspaceLayout } from "@/components/WorkspaceLayout";
import { LibraryLayout } from "@/components/LibraryLayout";
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

                {/* Compliance Workspace — daily operational hub */}
                <Route path="workspace" element={<WorkspaceLayout />}>
                  <Route index element={<Navigate to="tasks" replace />} />
                  <Route path="tasks" element={<TasksPage />} />
                  {/* Finance team home — same Tasks page, pre-scoped to
                      department=finance via the defaultDepartment prop. */}
                  <Route
                    path="finance"
                    element={<TasksPage defaultDepartment="finance" />}
                  />
                  {/* Backwards-compat for the original /workspace/queue URL */}
                  <Route path="queue" element={<Navigate to="/workspace/tasks" replace />} />
                  <Route path="calendar" element={<CalendarPage />} />
                  <Route path="licenses" element={<LicensesPage />} />
                  <Route path="documents" element={<DocumentsPage />} />
                </Route>

                {/* Regulatory Library — catalog + source regulations */}
                <Route path="library" element={<LibraryLayout />}>
                  <Route index element={<Navigate to="catalog" replace />} />
                  <Route path="catalog" element={<FilingsCatalogPage />} />
                  <Route path="regulations" element={<RegulationLibraryPage />} />
                </Route>

                {/* Entities live under Settings now, but keep deep links working */}
                <Route path="entities" element={<EntitiesPage />} />
                <Route path="entities/:entityId" element={<EntityDetailPage />} />

                {/* Admin — kept as separate sidebar group */}
                <Route
                  path="rules"
                  element={
                    <ProtectedRoute requireAdmin>
                      <RulesPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="audit-log"
                  element={
                    <ProtectedRoute requireAdmin>
                      <AuditLogPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="admin/users"
                  element={<Navigate to="/settings?tab=users" replace />}
                />

                {/* Backwards-compat redirects for old URLs / bookmarks */}
                <Route path="tasks" element={<Navigate to="/workspace/queue" replace />} />
                <Route path="calendar" element={<Navigate to="/workspace/calendar" replace />} />
                <Route path="licenses" element={<Navigate to="/workspace/licenses" replace />} />
                <Route path="documents" element={<Navigate to="/workspace/documents" replace />} />
                <Route path="catalog" element={<Navigate to="/library/catalog" replace />} />
                <Route path="regulations" element={<Navigate to="/library/regulations" replace />} />

                {/* Obligation detail + Settings — leaf pages */}
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
