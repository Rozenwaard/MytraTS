export interface PremiumCard {
  count: number;
  man_days: number;
}

export interface PremiumSummary {
  period: string | null;
  periods: string[];
  cards: {
    engineers: PremiumCard;
    controllers: PremiumCard;
    drivers: PremiumCard;
  };
  missing: { staff_id: string; name: string; position: string }[];
}

export interface TabelUploadResult {
  success: boolean;
  period: string;
  stored: number;
}

export async function fetchPremiumSummary(period?: string): Promise<PremiumSummary> {
  const q = period ? `?period=${encodeURIComponent(period)}` : "";
  const res = await fetch(`/api/premium/summary${q}`, { credentials: "include" });
  if (!res.ok) throw new Error("Ошибка загрузки премии");
  return res.json();
}

export async function uploadTabel(file: File): Promise<TabelUploadResult> {
  const fd = new FormData();
  fd.append("data", file);
  const res = await fetch("/api/premium/tabel", {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!res.ok) {
    const j = await res.json().catch(() => null);
    throw new Error(j?.error || "Ошибка загрузки табеля");
  }
  return res.json();
}
