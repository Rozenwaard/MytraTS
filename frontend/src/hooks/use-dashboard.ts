import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { DashboardSummary } from "../api/dashboard";

export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => api<DashboardSummary>("/api/dashboard/summary"),
    staleTime: 60_000,
  });
}
