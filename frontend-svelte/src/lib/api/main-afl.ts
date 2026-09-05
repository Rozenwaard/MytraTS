export interface MainAflRow {
	task_number: string | null;
	task_source: string | null;
	task_type: string | null;
	work_type_in_task: string | null;
	address: string | null;
	municipal_district: string | null;
	house_type: string | null;
	personal_account: string | null;
	service_object_type: string | null;
	subscriber_name: string | null;
	meter_installation_place: string | null;
	meter_status: string | null;
	meter_ownership: string | null;
	violations: string | null;
	comment: string | null;
	executor: string | null;
	visit_reason: string | null;
	customer: string | null;
	task_output: string | null;
	task_report: string | null;
	grid: string | null;
	done_day: string | null;
	reestr_number: string | null;
	reestr_date: string | null;
	errors: string | null;
	norm: number | null;
}

export interface MainAflResponse {
	rows: MainAflRow[];
	total: number;
	page: number;
	per_page: number;
}

export interface MainAflParams {
	page?: number;
	per_page?: number;
	sort?: string;
	order?: string;
	search?: string;
	customer?: string;
	task_report?: string;
	executor_org?: string;
	executor_filter?: string;
	only_completed?: boolean;
	only_without_reestr?: boolean;
	done_day?: string;
	only_uncompleted?: boolean;
	reestr?: string;
	task_type?: string;
	exact?: string;
}

export function buildMainAflQuery(params: MainAflParams): string {
	const q = new URLSearchParams();
	if (params.page) q.set('page', String(params.page));
	if (params.per_page) q.set('per_page', String(params.per_page));
	if (params.sort) q.set('sort', params.sort);
	if (params.order) q.set('order', params.order);
	if (params.search) q.set('search', params.search);
	if (params.customer) q.set('customer', params.customer);
	if (params.task_report) q.set('task_report', params.task_report);
	if (params.executor_org) q.set('executor_org', params.executor_org);
	if (params.executor_filter) q.set('executor_filter', params.executor_filter);
	if (params.only_completed) q.set('only_completed', '1');
	if (params.only_without_reestr) q.set('only_without_reestr', '1');
	if (params.done_day) q.set('done_day', params.done_day);
	if (params.reestr) q.set('reestr', params.reestr);
	if (params.task_type) q.set('task_type', params.task_type);
	if (params.only_uncompleted) q.set('only_uncompleted', '1');
	if (params.exact) q.set('exact', params.exact);
	return q.toString();
}
