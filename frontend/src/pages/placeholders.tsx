import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

function Placeholder({ title, description }: { title: string; description: string }) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-muted-foreground mt-1">{description}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Coming next</CardTitle>
          <CardDescription>
            This page is wired into the auth-gated API but the visuals from the
            Aspora mockups land in the next phase.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-dashed border-border bg-secondary/30 p-8 text-sm text-muted-foreground">
            Content lands here in Phase 3.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export const DashboardPage = () => (
  <Placeholder
    title="Dashboard"
    description="Overdue, alerts, this week's filings — at a glance."
  />
);
export const CalendarPage = () => (
  <Placeholder
    title="Compliance Calendar"
    description="Month grid of obligations across entities and jurisdictions."
  />
);
export const EntitiesPage = () => (
  <Placeholder
    title="Entities"
    description="Every Aspora legal entity with active obligation counts."
  />
);
export const EntityDetailPage = () => (
  <Placeholder
    title="Entity Detail"
    description="Hero card with obligation counts, then tabs for Registrations / Compliance Items / Documents / Activity."
  />
);
export const TasksPage = () => (
  <Placeholder
    title="Tasks"
    description="Assigned to me, watching, completed, all."
  />
);
export const RulesPage = () => (
  <Placeholder
    title="Compliance Rules"
    description="Admin-managed rule templates that generate per-entity obligations."
  />
);
export const SettingsPage = () => (
  <Placeholder
    title="Settings"
    description="Workspace, users, integrations."
  />
);
