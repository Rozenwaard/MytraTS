import { api } from './client';

export interface SlaRow {
	code: string;
	task_report: string;
	quantity: number;
	resultative: number;
	houses: number | null;
	non_resultative_pct: number;
	smooth_coef: number;
	sla_coef: number;
	rate: number;
	rate_sla: number;
	sum_sla: number;
	reduction: number;
}

export interface SlaResult {
	month: string;
	resultativity: SlaRow[];
	deadlines: SlaRow[];
	totals: {
		base: number;
		sum_sla: number;
		reduction: number;
	};
}

export async function fetchSla(month?: string): Promise<SlaResult> {
	const q = month ? `?month=${encodeURIComponent(month)}` : '';
	return api<SlaResult>(`/api/reports/sla${q}`);
}

export function slaDownloadUrl(month: string): string {
	return `/api/reports/sla/download?month=${encodeURIComponent(month)}`;
}
