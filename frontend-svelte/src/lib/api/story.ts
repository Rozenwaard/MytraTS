import { api } from './client';

export interface StoryAflRow {
	task_number: string | null;
	task_type: string | null;
	work_type_in_task: string | null;
	created_at: string | null;
	address: string | null;
	municipal_district: string | null;
	house_type: string | null;
	personal_account: string | null;
	subscriber_name: string | null;
	meter_installation_place: string | null;
	meter_status: string | null;
	violations: string | null;
	comment: string | null;
	executor: string | null;
	executor_organization: string | null;
	visit_reason: string | null;
	customer: string | null;
	task_output: string | null;
	task_report: string | null;
	task_detail: string | null;
	grid: string | null;
	done_day: string | null;
	reestr_number: string | null;
	reestr_date: string | null;
	report: string | null;
}

export interface StoryFilterCount {
	value: string;
	count: number;
}

export interface StoryAflResponse {
	rows: StoryAflRow[];
	total: number;
	page: number;
	per_page: number;
	filter_counts: Record<string, StoryFilterCount[]>;
}

export interface StoryAflParams {
	page?: number;
	per_page?: number;
	search?: string;
	period_month?: string;
	period_year?: string;
	customer?: string;
	task_report?: string;
	task_type?: string;
	grid?: string;
	house_type?: string;
	municipal_district?: string;
	meter_installation_place?: string;
	executor_organization?: string;
	executor?: string;
	report?: string;
	task_detail?: string;
}

export function buildStoryAflQuery(params: StoryAflParams): string {
	const q = new URLSearchParams();
	if (params.page) q.set('page', String(params.page));
	if (params.per_page) q.set('per_page', String(params.per_page));
	if (params.search) q.set('search', params.search);
	if (params.period_month) q.set('period_month', params.period_month);
	if (params.period_year) q.set('period_year', params.period_year);
	if (params.customer) q.set('customer', params.customer);
	if (params.task_report) q.set('task_report', params.task_report);
	if (params.task_type) q.set('task_type', params.task_type);
	if (params.grid) q.set('grid', params.grid);
	if (params.house_type) q.set('house_type', params.house_type);
	if (params.municipal_district) q.set('municipal_district', params.municipal_district);
	if (params.meter_installation_place) q.set('meter_installation_place', params.meter_installation_place);
	if (params.executor_organization) q.set('executor_organization', params.executor_organization);
	if (params.executor) q.set('executor', params.executor);
	if (params.report) q.set('report', params.report);
	if (params.task_detail) q.set('task_detail', params.task_detail);
	return q.toString();
}

export async function fetchStoryAfl(params: StoryAflParams = {}): Promise<StoryAflResponse> {
	return api<StoryAflResponse>(`/api/story-afl?${buildStoryAflQuery(params)}`);
}

export async function rejectStoryRows(
	taskNumbers: string[]
): Promise<{ success: boolean; updated: number }> {
	return api<{ success: boolean; updated: number }>('/api/story-afl/reject', {
		method: 'POST',
		body: JSON.stringify({ task_numbers: taskNumbers })
	});
}
