import { api } from './client';

export interface DashboardOverview {
	total: number;
	psk: number;
	rle: number;
	plan: number;
	unplan: number;
	completed: number;
	uncompleted: number;
	with_errors: number;
	without_errors: number;
	cost: number;
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
