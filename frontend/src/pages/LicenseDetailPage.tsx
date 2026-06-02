// Full-page license detail (revamp Phase 5 — replaces the pop-up). Fetches
// the license by id and renders the shared LicenseDetailBody, which holds the
// summary, the hierarchical filterable regulations table, AI extract +
// schedule-all, and delete.
import { useNavigate, useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Skeleton } from "@/components/ui/skeleton";
import { LicenseDetailBody } from "@/pages/LicensesPage";
import type { License } from "@/types/api";

export function LicenseDetailPage() {
  const { licenseId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const {
    data: license,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["license", licenseId],
    queryFn: () => api.get<License>(`/api/licenses/${licenseId}`),
    enabled: !!licenseId,
  });

  return (
    <div className="space-y-4">
      <Link
        to="/licenses"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Licenses
      </Link>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : !license ? (
        <div className="rounded-lg border border-border bg-secondary/30 px-4 py-6 text-sm text-muted-foreground">
          License not found.
        </div>
      ) : (
        <LicenseDetailBody
          license={license}
          isAdmin={isAdmin}
          onChanged={() => {
            // After delete the license is gone → go back to the list.
            // After other changes just refresh this page's data.
            refetch().then((r) => {
              if (!r.data) navigate("/licenses");
            });
          }}
        />
      )}
    </div>
  );
}
