export interface MainAflRow {
  task_number: string | null;
  task_source: string | null;
  task_type: string | null;
  work_type_in_task: string | null;
  address: string | null;
  municipal_district: string | null;
  house_type: string | null;
  personal_account: string | null;
  service_object_type: string | null;
  subscriber_name: string | null;
  meter_installation_place: string | null;
  meter_status: string | null;
  meter_ownership: string | null;
  violations: string | null;
  comment: string | null;
  executor: string | null;
  visit_reason: string | null;
  customer: string | null;
  task_output: string | null;
  task_report: string | null;
  grid: string | null;
  done_day: string | null;
  reestr_number: string | null;
  reestr_date: string | null;
  errors: string | null;
}

export interface MainAflResponse {
  rows: MainAflRow[];
  total: number;
  page: number;
  per_page: number;
}

export interface MainAflParams {
  page?: number;
  per_page?: number;
  sort?: string;
  order?: string;
  search?: string;
  customer?: string;
  task_report?: string;
  executor_org?: string;
  executor_filter?: string;
  only_completed?: boolean;
  only_without_reestr?: boolean;
  done_day?: string;
  only_uncompleted?: boolean;
  reestr?: string;
  task_type?: string;
}



export interface ReestrResult {
  task_report: string;
  reestr_number: string;
  count: number;
  skipped: number;
  rejected: number;
}

export async function createReestr(taskNumbers: string[]) {
  const res = await fetch("/api/reestr", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ task_numbers: taskNumbers }),
  });
  if (!res.ok) throw new Error("Ошибка создания реестра");
  return res.json() as Promise<{ success: boolean; reestrs: ReestrResult[]; reestr_date: string; blocked: string[] }>;
}

export async function resetReestr(taskNumbers: string[]) {
  const res = await fetch("/api/reestr/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ task_numbers: taskNumbers }),
  });
  if (!res.ok) throw new Error("Ошибка сброса реестра");
  return res.json() as Promise<{ success: boolean; cleared: number }>;
}

export async function fetchReestrList(): Promise<{ reestrs: string[]; meta: Record<string, { task_report: string | null; customer: string | null }> }> {
  const res = await fetch("/api/reestr-list", { credentials: "include" });
  if (!res.ok) return { reestrs: [], meta: {} };
  return res.json();
}

export function downloadReestrUrl(rn: string) {
  return `/api/download-reestr/${encodeURIComponent(rn)}`;
}



export interface MainAflStats {
  customers: Record<string, number>;
  plan: number;
  unplan: number;
  with_reestr: number;
  without_reestr: number;
  completed: number;
  uncompleted: number;
  task_reports: { label: string; count: number }[];
  executors: { label: string; count: number; locale: string | null }[];
  depts: { label: string; count: number }[];
  done_days: string[];
}
