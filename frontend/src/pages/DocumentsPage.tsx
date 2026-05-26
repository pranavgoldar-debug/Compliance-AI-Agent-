import { FolderOpen, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

export function DocumentsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Documents"
        description="Filings, certificates, and audit artifacts across every entity."
      />
      <Card>
        <CardContent className="p-10">
          <EmptyState
            icon={<FolderOpen className="h-6 w-6" />}
            title="Document storage arrives in Phase 5"
            description={
              <>
                Upload proof-of-filing PDFs, prior-year submissions, and expert
                notes here. Each document links to an entity or specific
                obligation so it's discoverable from the obligation drawer too.
              </>
            }
            action={
              <Button variant="outline" disabled>
                <Upload className="h-4 w-4" />
                Upload — coming soon
              </Button>
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}
