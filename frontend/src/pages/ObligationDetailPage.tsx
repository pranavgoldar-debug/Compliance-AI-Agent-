// Full-page view of an obligation. Shares its body with the side-panel drawer
// (see components/ObligationDetail.tsx) so they stay in lockstep.
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ObligationDetail } from "@/components/ObligationDetail";

export function ObligationDetailPage() {
  const { obligationId } = useParams();
  const id = Number(obligationId);
  if (!id || Number.isNaN(id)) {
    return (
      <div className="space-y-3">
        <Link to="/calendar" className="text-sm text-aspora-700 hover:underline">
          ← Back to calendar
        </Link>
        <div className="rounded-xl border border-border bg-card p-10 text-center text-muted-foreground">
          Obligation not found.
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <Link
        to="/tasks"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to tasks
      </Link>
      <ObligationDetail obligationId={id} variant="page" />
    </div>
  );
}
