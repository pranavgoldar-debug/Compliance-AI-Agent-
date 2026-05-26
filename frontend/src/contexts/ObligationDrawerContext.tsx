import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface DrawerState {
  obligationId: number | null;
  openObligation: (id: number) => void;
  closeObligation: () => void;
}

const Ctx = createContext<DrawerState | undefined>(undefined);

export function ObligationDrawerProvider({ children }: { children: ReactNode }) {
  const [obligationId, setObligationId] = useState<number | null>(null);

  const openObligation = useCallback((id: number) => setObligationId(id), []);
  const closeObligation = useCallback(() => setObligationId(null), []);

  const value = useMemo<DrawerState>(
    () => ({ obligationId, openObligation, closeObligation }),
    [obligationId, openObligation, closeObligation],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useObligationDrawer(): DrawerState {
  const ctx = useContext(Ctx);
  if (ctx === undefined) {
    throw new Error("useObligationDrawer must be used inside <ObligationDrawerProvider>");
  }
  return ctx;
}
