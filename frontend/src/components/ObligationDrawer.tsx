// Thin wrapper — renders the shared ObligationDetail body inside a Radix Dialog
// that slides in from the right (the ~480px side panel).
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ObligationDetail } from "@/components/ObligationDetail";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";

export function ObligationDrawer() {
  const { obligationId, closeObligation } = useObligationDrawer();
  return (
    <Dialog open={obligationId !== null} onOpenChange={(open) => !open && closeObligation()}>
      <DialogContent side="right" hideCloseButton className="p-0 w-[760px] max-w-[95vw]">
        {obligationId !== null && (
          <ObligationDetail
            obligationId={obligationId}
            variant="drawer"
            onClose={closeObligation}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
