export interface FinCardData {
  total: number;
  by_locale: { locale: string; count: number }[];
  cost: number;
}

export interface FinReportData {
  cards: {
    completed: FinCardData;
    without_reestr: FinCardData;
    with_errors: FinCardData;
    ready: FinCardData;
  };
  work_types: { label: string; count: number }[];
  total_cost: number;
  cost_psk: number;
  cost_rle: number;
}

export async function fetchFinReport(period: string): Promise<FinReportData> {
  const res = await fetch(`/api/fin-report?period=${encodeURIComponent(period)}`, { credentials: "include" });
  if (!res.ok) throw new Error("Ошибка загрузки финотчёта");
  return res.json();
}

export async function addToReport(period: string): Promise<{ success: boolean; updated: number; period: string }> {
  const res = await fetch("/api/fin-report/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ period }),
  });
  if (!res.ok) throw new Error("Ошибка добавления в отчёт");
  return res.json();
}

export async function uploadDiscrepancies(file: File): Promise<{ success: boolean; updated: number; not_found: number }> {
  const fd = new FormData();
  fd.append("data", file);
  const res = await fetch("/api/fin-report/discrepancies", {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!res.ok) throw new Error("Ошибка загрузки разногласий");
  return res.json();
}

export function startFinReportDownload(period: string): Promise<{ download_id: string }> {
  return fetch("/api/fin-report/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ period }),
  }).then((res) => {
    if (!res.ok) throw new Error("Ошибка запуска выгрузки");
    return res.json();
  });
}

export function fetchFinReportDownloadProgress(downloadId: string): Promise<{ status: string; done: number; total: number; progress: number; message?: string }> {
  return fetch(`/api/fin-report/download/progress/${downloadId}`, { credentials: "include" }).then((res) => {
    if (!res.ok) throw new Error("Ошибка прогресса");
    return res.json();
  });
}

export function finReportDownloadResultUrl(downloadId: string): string {
  return `/api/fin-report/download/result/${downloadId}`;
}
