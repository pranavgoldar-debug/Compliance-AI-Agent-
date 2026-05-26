import { ScrollText } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

export function AuditLogPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit Log"
        description="Immutable record of every state change across the workspace."
      />
      <Card>
        <CardContent className="p-10">
          <EmptyState
            icon={<ScrollText className="h-6 w-6" />}
            title="Full audit log lands in Phase 5"
            description={
              <>
                Backend already records every status change, assignment, and
                comment. The UI to view a filterable chronological feed (with
                before → after diff pills) is the next thing we ship.
              </>
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}
