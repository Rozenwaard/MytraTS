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

/**
 * «Реестр показаний»: xlsx показаний и нарушений РЛЭ за текущий месяц.
 */
export async function fetchReadingsRegister(): Promise<{ blob: Blob; filename: string }> {
	const res = await fetch('/api/rle/readings', { credentials: 'include' });
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка выгрузки «Реестр показаний»');
	}
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') ?? '';
	const m = disposition.match(/filename\*=UTF-8''([^;]+)/);
	const filename = m ? decodeURIComponent(m[1]) : 'Реестр показаний и нарушений.xlsx';
	return { blob, filename };
}

export interface RlePeriod {
	value: string;
	has_rows: boolean;
	is_current: boolean;
	is_archived: boolean;
	category: 'current' | 'previous' | 'old';
	can_form: boolean;
}

export interface RlePeriods {
	periods: RlePeriod[];
	default: string;
}

/**
 * Карусель месяцев для «Отчёта о выполнении» (те же периоды, что в Финотчёте).
 */
export async function fetchRlePeriods(): Promise<RlePeriods> {
	return api<RlePeriods>('/api/rle/periods');
}

/**
 * «Отчёт о выполнении»: xlsx со сводом и реестром по выбранным месяцам.
 */
export async function downloadExecutionReport(
	periods: string[]
): Promise<{ blob: Blob; filename: string }> {
	const res = await fetch('/api/rle/report/download', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ periods })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка выгрузки «Отчёт о выполнении»');
	}
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') ?? '';
	const m = disposition.match(/filename\*=UTF-8''([^;]+)/);
	const filename = m ? decodeURIComponent(m[1]) : 'Отчёт о выполнении РЛЭ.xlsx';
	return { blob, filename };
}

/**
 * «Общая производительность»: все заказчики, свод по отделениям + реестр.
 */
export async function downloadProductivityReport(
	periods: string[]
): Promise<{ blob: Blob; filename: string }> {
	const res = await fetch('/api/rle/productivity/download', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ periods })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка выгрузки «Общая производительность»');
	}
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') ?? '';
	const m = disposition.match(/filename\*=UTF-8''([^;]+)/);
	const filename = m ? decodeURIComponent(m[1]) : 'Общая производительность.xlsx';
	return { blob, filename };
}
