const BASE = "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.error ?? res.statusText);
  }
  if (res.headers.get("content-type")?.includes("application/json")) {
    return res.json();
  }
  return undefined as T;
}

export interface User {
  id: number;
  full_name: string;
  dept: string;
  locale: string | null;
  position: string;
  staff_id: string;
  role: "администратор" | "специалист" | "менеджер" | "оператор";
}
