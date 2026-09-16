import { api } from './client';

export interface RleWeek {
	week: number;
	range: string;
}

export interface RleCell {
	count: number;
	per_executor: number;
	per_day: number;
	workers: number;
}

export interface RleRow {
	grid: string;
	values: RleCell[];
}

export interface RleTotal {
	count: number;
	per_executor: number;
	per_day: number;
	executors: number;
}

export interface RleData {
	weeks: RleWeek[];
	grids: string[];
	rows: RleRow[];
	totals: RleTotal[];
}

export async function fetchRle(): Promise<RleData> {
	return api<RleData>('/api/rle');
}

/**
 * «Загрузить 1С»: файл с работами РЛЭ → сводный отчёт (xlsx, вкладки «КСП» и «ИП»).
 * Отдельный fetch: multipart требует, чтобы браузер сам выставил Content-Type с boundary.
 */
export async function uploadRle(file: File): Promise<{ blob: Blob; filename: string }> {
	const form = new FormData();
	form.append('data', file);
	const res = await fetch('/api/rle/upload', {
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
	const filename = m ? decodeURIComponent(m[1]) : 'РЛЭ.xlsx';
	return { blob, filename };
}
