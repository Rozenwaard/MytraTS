export interface RleWeek {
  week: number;
  range: string;
}

export interface RleCell {
  count: number;
  per_executor: number;
  per_day: number;
}

export interface RleRow {
  grid: string;
  values: RleCell[];
}

export interface RleTotal {
  count: number;
  executors: number;
}

export interface RleData {
  weeks: RleWeek[];
  grids: string[];
  rows: RleRow[];
  totals: RleTotal[];
}

export async function fetchRle(): Promise<RleData> {
  const res = await fetch("/api/rle", { credentials: "include" });
  if (!res.ok) throw new Error("Ошибка загрузки РЛЭ");
  return res.json();
}

export function rleDownloadUrl(): string {
  return "/api/rle/download";
}
