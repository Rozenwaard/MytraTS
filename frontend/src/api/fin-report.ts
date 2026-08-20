export interface FinCardData {
  total: number;
  by_locale: { locale: string; count: number }[];
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
