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
import { LicensesPage } from "@/pages/LicensesPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Longer staleTime → cached lists render instantly on tab switch
      // (no spinner) while a background refetch updates them. Pages that
      // need fresher data override this per-query.
      staleTime: 2 * 60_000,
      gcTime: 10 * 60_000,
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
                {/* Flat IA — 4 daily-use pages at the top level */}
                <Route index element={<DashboardPage />} />
                <Route path="licenses" element={<LicensesPage />} />
                <Route path="calendar" element={<CalendarPage />} />
                {/* Combined Compliance & Finance — one Tasks page where
                    both teams work. The Awaiting payment chip is the
                    main slicer for the finance side. */}
                <Route path="tasks" element={<TasksPage />} />
                {/* Backwards-compat: split routes from the previous PR */}
                <Route
                  path="compliance"
                  element={<Navigate to="/tasks" replace />}
                />
                <Route
                  path="finance"
                  element={<Navigate to="/tasks?awaiting_payment=1" replace />}
                />

                {/* Admin pages */}
                <Route path="entities" element={<EntitiesPage />} />
                <Route path="entities/:entityId" element={<EntityDetailPage />} />
                <Route
                  path="rules"
                  element={
                    <ProtectedRoute requireAdmin>
                      <RulesPage />
                    </ProtectedRoute>
                  }
                />
                <Route path="documents" element={<DocumentsPage />} />
                <Route path="regulations" element={<RegulationLibraryPage />} />
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

                {/* Backwards-compat redirects for the old Workspace shell URLs */}
                <Route path="workspace" element={<Navigate to="/compliance" replace />} />
                <Route
                  path="workspace/tasks"
                  element={<Navigate to="/tasks" replace />}
                />
                <Route
                  path="workspace/queue"
                  element={<Navigate to="/tasks" replace />}
                />
                <Route
                  path="workspace/finance"
                  element={<Navigate to="/tasks?awaiting_payment=1" replace />}
                />
                <Route
                  path="workspace/calendar"
                  element={<Navigate to="/calendar" replace />}
                />
                <Route
                  path="workspace/licenses"
                  element={<Navigate to="/licenses" replace />}
                />
                <Route
                  path="workspace/documents"
                  element={<Navigate to="/documents" replace />}
                />
                <Route
                  path="library"
                  element={<Navigate to="/regulations" replace />}
                />
                <Route
                  path="library/catalog"
                  element={<Navigate to="/rules" replace />}
                />
                <Route
                  path="library/regulations"
                  element={<Navigate to="/regulations" replace />}
                />
                <Route path="catalog" element={<Navigate to="/rules" replace />} />

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
