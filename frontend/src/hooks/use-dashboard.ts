import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { DashboardSummary, DashboardOverview } from "../api/dashboard";

export function useDashboardSummary(dept?: string) {
  const q = dept ? `?dept=${encodeURIComponent(dept)}` : "";
  return useQuery({
    queryKey: ["dashboard-summary", dept],
    queryFn: () => api<DashboardSummary>(`/api/dashboard/summary${q}`),
    staleTime: 60_000,
  });
}

export function useDepartments(enabled: boolean) {
  return useQuery({
    queryKey: ["departments"],
    queryFn: () => api<string[]>("/api/executor-organizations"),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useDashboardOverview() {
  return useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => api<DashboardOverview>("/api/dashboard/overview"),
    staleTime: 60_000,
  });
}
