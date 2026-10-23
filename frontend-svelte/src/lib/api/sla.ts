import { api } from './client';

export interface SlaRow {
	task_report: string;
	quantity: number;
	resultative: number;
	nedopusk: number;
	limit: number;
	fullness: number;
	sroki: number;
	coef: number;
	loss: number;
	overcap: number;
}

export interface SlaResult {
	month: string;
	rows: SlaRow[];
	totals: {
		loss: number;
		overcap: number;
		total: number;
	};
}

export async function fetchSla(month?: string): Promise<SlaResult> {
	const q = month ? `?month=${encodeURIComponent(month)}` : '';
	return api<SlaResult>(`/api/reports/sla${q}`);
}

export function slaDownloadUrl(month: string): string {
	return `/api/reports/sla/download?month=${encodeURIComponent(month)}`;
}
