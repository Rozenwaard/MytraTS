import { api } from './client';

export interface DebtMatrix {
	total: number;
	ontime_in_work: number;
	ontime_completed: number;
	overdue_in_work: number;
	overdue_completed: number;
}

export interface InWorkMatrix {
	psk_plan: number;
	psk_unplan: number;
	rle_plan: number;
	rle_unplan: number;
}

export interface Workers {
	total: number;
	controllers: number;
	engineers: number;
}

export interface Instrumental {
	ordered: number;
	completed: number;
}

export interface DashboardOverview {
	cost: number;
	cost_psk: number;
	cost_rle: number;
	in_work_matrix: InWorkMatrix;
	debt: DebtMatrix;
	workers: Workers;
	instrumental: Instrumental;
	duplicates: {
		crm: number;
		mixed: number;
		non_crm: number;
	};
}

export async function fetchDashboardOverview(): Promise<DashboardOverview> {
	return api<DashboardOverview>('/api/dashboard/overview');
}

export interface ErrorsByLocaleItem {
	locale: string;
	count: number;
}

export interface ErrorsByLocale {
	total: number;
	by_locale: ErrorsByLocaleItem[];
}

export async function fetchErrorsByLocale(): Promise<ErrorsByLocale> {
	return api<ErrorsByLocale>('/api/dashboard/errors-by-locale');
}
