import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/PageHeader";
import { useAuth } from "@/contexts/AuthContext";

export function SettingsPage() {
  const { user } = useAuth();
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Workspace, users, and integrations. Admin-only."
      />
      <Card>
        <CardContent className="p-6 space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Your account
          </h3>
          <dl className="grid grid-cols-2 gap-y-3 text-sm max-w-md">
            <dt className="text-muted-foreground">Name</dt>
            <dd>{user?.full_name || "—"}</dd>
            <dt className="text-muted-foreground">Email</dt>
            <dd>{user?.email}</dd>
            <dt className="text-muted-foreground">Role</dt>
            <dd className="capitalize">{user?.role}</dd>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          User management, workspace settings, integrations and audit-log export
          land in Phase 4.
        </CardContent>
      </Card>
    </div>
  );
}
