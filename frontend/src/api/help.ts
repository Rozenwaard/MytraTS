export interface HelpBlock {
  type: "p" | "table" | "h";
  text?: string;
  rows?: string[][];
  menu?: string;
}

export interface HelpPageData {
  key: string;
  title: string;
  updated_at: string | null;
  blocks: HelpBlock[];
}

export async function fetchHelpPage(key: string): Promise<HelpPageData> {
  const res = await fetch(`/api/help/${key}`, { credentials: "include" });
  if (!res.ok) throw new Error("Ошибка загрузки страницы");
  return res.json();
}

export async function uploadHelpPage(key: string, file: File): Promise<{ success: boolean; key: string; updated_at: string }> {
  const fd = new FormData();
  fd.append("data", file);
  const res = await fetch(`/api/help/${key}`, { method: "POST", credentials: "include", body: fd });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? "Ошибка загрузки");
  }
  return res.json();
}
