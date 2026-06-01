// Shared hook: is the AI gate open in this deployment?
//
// Mirrors the server-side compliance_agent.ai.ai_available() check by
// reading /api/system/info (which the topbar also polls). Cached.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SystemInfo } from "@/types/api";


export function useAiAvailable() {
  const { data } = useQuery({
    queryKey: ["system-info"],
    queryFn: () => api.get<SystemInfo>("/api/system/info"),
    staleTime: 5 * 60_000,
  });
  return {
    available: data?.ai_available ?? false,
    mode: data?.mode ?? "mock",
    tooltip:
      data && data.ai_available
        ? "Runs on Grok with your ANTHROPIC_API_KEY."
        : "AI is off. Set COMPLIANCE_AGENT_LIVE=1 + ANTHROPIC_API_KEY to enable.",
  };
}
