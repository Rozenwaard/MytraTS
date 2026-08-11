import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { MainAflParams, MainAflResponse } from "../api/main-afl";

function buildQuery(params: MainAflParams): string {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.per_page) q.set("per_page", String(params.per_page));
  if (params.sort) q.set("sort", params.sort);
  if (params.order) q.set("order", params.order);
  if (params.search) q.set("search", params.search);
  if (params.customer) q.set("customer", params.customer);
  if (params.task_report) q.set("task_report", params.task_report);
  if (params.executor_org) q.set("executor_org", params.executor_org);
  if (params.executor_filter) q.set("executor_filter", params.executor_filter);
  if (params.only_completed) q.set("only_completed", "1");
  if (params.only_without_reestr) q.set("only_without_reestr", "1");
  return q.toString();
}

export function useMainAfl(params: MainAflParams) {
  return useQuery({
    queryKey: ["main-afl", params],
    queryFn: () => api<MainAflResponse>(`/api/main-afl?${buildQuery(params)}`),
    placeholderData: (prev) => prev,
  });
}
