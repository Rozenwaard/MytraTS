import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ReportCheckResponse } from "../api/report";

export function useReportCheck() {
  return useQuery({
    queryKey: ["report-check"],
    queryFn: () => api<ReportCheckResponse>("/api/report/check"),
    staleTime: 60_000,
  });
}
