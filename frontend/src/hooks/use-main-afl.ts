import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { buildMainAflQuery } from "../api/main-afl";
import type { MainAflParams, MainAflResponse, MainAflStats } from "../api/main-afl";

export function useMainAfl(params: MainAflParams) {
  return useQuery({
    queryKey: ["main-afl", params],
    queryFn: () => api<MainAflResponse>(`/api/main-afl?${buildMainAflQuery(params)}`),
    placeholderData: (prev) => prev,
  });
}

export function useMainAflStats() {
  return useQuery({
    queryKey: ["main-afl-stats"],
    queryFn: () => api<MainAflStats>("/api/main-afl/stats"),
    staleTime: 60_000,
  });
}
