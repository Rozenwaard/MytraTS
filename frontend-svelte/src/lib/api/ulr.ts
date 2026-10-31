export type WorkTypeOption = { short: string; title: string; customer: string | null };
export type UlrOptions = { customers: string[]; subdivisions: Record<string, string[]>; work_types: WorkTypeOption[]; assignment_types: Record<string, string[]> };

export type UlrFeedbackItem = {
	row: number;
	object_code: string | null;
	meter_serial_number: string | null;
	tu_number: string | null;
	reason: string;
};
export type UlrUploadResult = {
	inserted: number;
	feedback: UlrFeedbackItem[];
	total: number;
	feedback_file_base64?: string;
	feedback_filename?: string;
};

export async function fetchUlrOptions(): Promise<UlrOptions> {
	const res = await fetch('/api/ulr/options', { credentials: 'include' });
	if (!res.ok) throw new Error('Не удалось получить справочники');
	return res.json();
}

export async function uploadUlr(
	fields: { customer: string; letter_number: string; letter_date: string; work_type_in_task: string; subdivision: string; task_type: string },
	file: File
): Promise<UlrUploadResult> {
	const form = new FormData();
	form.append('customer', fields.customer);
	form.append('letter_number', fields.letter_number);
	form.append('letter_date', fields.letter_date);
	form.append('work_type_in_task', fields.work_type_in_task);
	form.append('subdivision', fields.subdivision);
	form.append('task_type', fields.task_type);
	form.append('file', file);

	const res = await fetch('/api/ulr/upload', { method: 'POST', credentials: 'include', body: form });
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки');
	}
	return res.json();
}

export type WorkReportOption = { id: number | null; short: string | null; needs_co: boolean };

export type UlrExecutionRow = {
	task_number: string | null;
	task_source: string | null;
	task_type: string | null;
	work_type_in_task: string | null;
	created_at: string | null;
	due_date: string | null;
	customer: string | null;
	visit_reason: string | null;
	subscriber_type: string | null;
	grid: string | null;
	personal_account: string | null;
	service_object_type: string | null;
	subscriber_name: string | null;
	address: string | null;
	meter_model: string | null;
	meter_installation_place: string | null;
	violations: string | null;
	meter_type: string | null;
	executor: string | null;
	executor_organization: string | null;
	co_executor: string | null;
	task_report: string | null;
	done_day: string | null;
	reestr_number: string | null;
	status: string | null;
	contract_status: string | null;
	norm: number | null;
	work_type_options: WorkReportOption[];
	executor_options: string[];
	co_executor_required: boolean;
};

export async function fetchUlrExecution(): Promise<{ rows: UlrExecutionRow[] }> {
	const res = await fetch('/api/ulr/execution', { credentials: 'include' });
	if (!res.ok) throw new Error('Не удалось получить список');
	return res.json();
}

export async function updateUlrExecution(fields: {
	task_number: string;
	executor: string | null;
	co_executor: string | null;
	task_report: string | null;
	done_day: string | null;
	violations: string | null;
}): Promise<{ success: boolean; status: string }> {
	const res = await fetch('/api/ulr/execution', {
		method: 'PATCH',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(fields)
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка сохранения');
	}
	return res.json();
}

export type UlrReestrResult = {
	success: boolean;
	reestrs: { name: string; reestr_number: string; count: number }[];
	skipped: number;
	reestr_date: string;
};

export async function createUlrReestr(taskNumbers: string[]): Promise<UlrReestrResult> {
	const res = await fetch('/api/ulr/reestr', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ task_numbers: taskNumbers })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка создания реестра');
	}
	return res.json();
}

export async function resetUlrReestr(taskNumbers: string[]): Promise<{ success: boolean; cleared: number }> {
	const res = await fetch('/api/ulr/reestr/reset', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ task_numbers: taskNumbers })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка удаления из реестра');
	}
	return res.json();
}

export async function changeUlrTaskReport(taskNumber: string, taskReport: string): Promise<{ success: boolean }> {
	const res = await fetch('/api/ulr/task-report', {
		method: 'PATCH',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ task_number: taskNumber, task_report: taskReport })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка замены вида работ');
	}
	return res.json();
}

export async function changeUlrDueDate(taskNumbers: string[], dueDate: string): Promise<{ success: boolean; updated: number }> {
	const res = await fetch('/api/ulr/due-date', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ task_numbers: taskNumbers, due_date: dueDate })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка изменения даты');
	}
	return res.json();
}
