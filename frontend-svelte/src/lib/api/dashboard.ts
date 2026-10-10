import { api } from './client';
import type { MainAflResponse } from './main-afl';

export interface DebtMatrix {
	total: number;
	ontime_in_work: number;
	ontime_completed: number;
	overdue_in_work: number;
	overdue_completed: number;
}

export interface DebtMonth {
	period: string;
	received: number;
	completed: number;
	on_time: number;
}

export interface InWorkMatrix {
	psk_plan: number;
	psk_unplan: number;
	rle_plan: number;
	rle_unplan: number;
}

export interface Workers {
	total: number;
}

export interface NewUsers {
	review: number;
}

export interface Instrumental {
	ordered: number;
	completed: number;
}

export interface NedopuskItem {
	id: number;
	label: string;
	percent: number | null;
}

export interface DashboardOverview {
	cost: number;
	cost_psk: number;
	cost_rle: number;
	in_work_matrix: InWorkMatrix;
	debt: DebtMatrix;
	workers: Workers;
	tickets: { unanswered: number };
	new_users: NewUsers;
	instrumental: Instrumental;
	duplicates: {
		crm: number;
		mixed: number;
		non_crm: number;
	};
	nedopuski: NedopuskItem[];
}

export async function fetchDashboardOverview(): Promise<DashboardOverview> {
	return api<DashboardOverview>('/api/dashboard/overview');
}

export async function fetchDebtMonth(): Promise<DebtMonth> {
	return api<DebtMonth>('/api/dashboard/debt-month');
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

export interface StatusState {
	last_txt_count: string | null;
	in_work_at: string | null;
	in_work_count: string | null;
	new_tasks_at: string | null;
	new_tasks_count: string | null;
}

export async function fetchStatus(): Promise<StatusState> {
	return api<StatusState>('/api/status');
}

export interface Priorities {
	priorities: string[];
}

export async function fetchPriorities(): Promise<Priorities> {
	return api<Priorities>('/api/dashboard/priorities');
}

export async function savePriorities(items: string[]): Promise<Priorities> {
	return api<Priorities>('/api/dashboard/priorities', {
		method: 'POST',
		body: JSON.stringify({ priorities: items })
	});
}

export interface InWorkParams {
	page?: number;
	per_page?: number;
	sort?: string;
	order?: string;
	search?: string;
	customer?: string;
	task_report?: string;
	task_type?: string;
	executor_org?: string;
	executor_filter?: string;
	done_day?: string;
	exact?: string;
	revoked?: boolean;
	queue?: string;
	status?: string;
}

export function buildInWorkQuery(params: InWorkParams): string {
	const q = new URLSearchParams();
	if (params.page) q.set('page', String(params.page));
	if (params.per_page) q.set('per_page', String(params.per_page));
	if (params.sort) q.set('sort', params.sort);
	if (params.order) q.set('order', params.order);
	if (params.search) q.set('search', params.search);
	if (params.customer) q.set('customer', params.customer);
	if (params.task_report) q.set('task_report', params.task_report);
	if (params.task_type) q.set('task_type', params.task_type);
	if (params.executor_org) q.set('executor_org', params.executor_org);
	if (params.executor_filter) q.set('executor_filter', params.executor_filter);
	if (params.done_day) q.set('done_day', params.done_day);
	if (params.exact) q.set('exact', params.exact);
	if (params.revoked) q.set('revoked', '1');
	if (params.queue) q.set('queue', params.queue);
	if (params.status) q.set('status', params.status);
	return q.toString();
}

export async function fetchInWork(params: InWorkParams = {}): Promise<MainAflResponse> {
	return api<MainAflResponse>(`/api/dashboard/in-work?${buildInWorkQuery(params)}`);
}

export interface InWorkQueueItem {
	label: string;
	value: string;
	count: number;
}

export interface InWorkStatusItem {
	label: string;
	count: number;
}

export interface InWorkStats {
	customers: Record<string, number>;
	plan: number;
	unplan: number;
	revoked: number;
	queue: InWorkQueueItem[];
	statuses: InWorkStatusItem[];
	depts: string[];
	unenriched: number;
}

export async function fetchInWorkStats(): Promise<InWorkStats> {
	return api<InWorkStats>('/api/dashboard/in-work/stats');
}
