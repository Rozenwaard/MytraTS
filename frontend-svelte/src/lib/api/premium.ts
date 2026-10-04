import { api } from './client';

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
	const q = period ? `?period=${encodeURIComponent(period)}` : '';
	return api<PremiumSummary>(`/api/premium/summary${q}`);
}

export async function uploadTabel(file: File): Promise<TabelUploadResult> {
	const form = new FormData();
	form.append('data', file);
	const res = await fetch('/api/premium/tabel', {
		method: 'POST',
		credentials: 'include',
		body: form
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки табеля');
	}
	return (await res.json()) as TabelUploadResult;
}

export async function upload1c(
	file: File,
	period: string
): Promise<{ blob: Blob; filename: string }> {
	const form = new FormData();
	form.append('data', file);
	const res = await fetch(`/api/premium/upload-1c?period=${encodeURIComponent(period)}`, {
		method: 'POST',
		credentials: 'include',
		body: form
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки 1С');
	}
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') ?? '';
	const m = disposition.match(/filename\*=UTF-8''([^;]+)/);
	const filename = m ? decodeURIComponent(m[1]) : 'Отчёт_по_нормативам.xlsx';
	return { blob, filename };
}
