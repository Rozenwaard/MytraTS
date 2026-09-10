import { api } from './client';

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
	return api<FinReportData>(`/api/fin-report?period=${encodeURIComponent(period)}`);
}

export async function addToReport(
	period: string
): Promise<{ success: boolean; updated: number; period: string }> {
	return api('/api/fin-report/add', {
		method: 'POST',
		body: JSON.stringify({ period })
	});
}

export async function uploadDiscrepancies(
	file: File
): Promise<{ success: boolean; updated: number; not_found: number }> {
	const form = new FormData();
	form.append('data', file);
	const res = await fetch('/api/fin-report/discrepancies', {
		method: 'POST',
		credentials: 'include',
		body: form
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки разногласий');
	}
	return (await res.json()) as { success: boolean; updated: number; not_found: number };
}

export async function recheckTasks(
	file: File
): Promise<{ blob: Blob; updated: number; not_found: number }> {
	const form = new FormData();
	form.append('data', file);
	const res = await fetch('/api/fin-report/recheck', {
		method: 'POST',
		credentials: 'include',
		body: form
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка повторной проверки');
	}
	const blob = await res.blob();
	const updated = Number(res.headers.get('X-Updated') ?? '0');
	const not_found = Number(res.headers.get('X-Not-Found') ?? '0');
	return { blob, updated, not_found };
}

export interface FinReportDownloadProgress {
	status: string;
	done: number;
	total: number;
	progress: number;
	message?: string;
}

export function startFinReportDownload(period: string): Promise<{ download_id: string }> {
	return api('/api/fin-report/download', {
		method: 'POST',
		body: JSON.stringify({ period })
	});
}

export function fetchFinReportDownloadProgress(
	downloadId: string
): Promise<FinReportDownloadProgress> {
	return api<FinReportDownloadProgress>(`/api/fin-report/download/progress/${downloadId}`);
}

export async function fetchFinReportDownloadResult(downloadId: string): Promise<Blob> {
	const res = await fetch(`/api/fin-report/download/result/${downloadId}`, {
		credentials: 'include'
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка скачивания отчёта');
	}
	return res.blob();
}
