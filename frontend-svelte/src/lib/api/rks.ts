export type RksStats = {
	consumers: number;
	points: number;
	tasks: number;
	matched: number;
	ulr_ref: number;
};

export type RksUploadResult = {
	success: boolean;
	stats: RksStats & { matched_code: number; matched_address: number; unmatched: number };
	total: number;
};

export type RksConsumer = {
	id: number;
	contract_number: string | null;
	energy_object_code: string | null;
	fl_yul: string | null;
	department: string | null;
	consumer_name: string | null;
	phone: string | null;
	points_count: number;
};

export type WorkReportOption = { id: number | null; short: string | null; needs_co: boolean };

export type RksTask = {
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
	meter_serial_number: string | null;
	violations: string | null;
	meter_type: string | null;
	has_current_transformer: string | null;
	meter_status: string | null;
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

export type RksOptions = {
	customers: string[];
	subdivisions: Record<string, string[]>;
	work_types: { short: string; title: string; customer: string | null }[];
	assignment_types: Record<string, string[]>;
};

export type ObjectPoint = { tu_id: string; tu_number: string; active_task: string | null };

export const ASSIGNMENT_LABELS: Record<string, string> = {
	'КСП': 'Снятие контрольных показаний',
	'ИП': 'Инструментальная проверка',
	'Опломбировка': 'Опломбировка',
	'Распломбировка': 'Распломбировка'
};

export function assignmentLabel(value: string | null | undefined): string {
	if (!value) return '';
	return ASSIGNMENT_LABELS[value] ?? value;
}

export async function uploadRks(file: File, ulrFile: File | null, taskType: string): Promise<RksUploadResult> {
	const form = new FormData();
	form.append('file', file);
	if (ulrFile) form.append('ulr_file', ulrFile);
	if (taskType) form.append('task_type', taskType);
	const res = await fetch('/api/rks/upload', { method: 'POST', credentials: 'include', body: form });
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки');
	}
	return res.json();
}

export async function fetchRksSummary(): Promise<RksStats> {
	const res = await fetch('/api/rks/summary', { credentials: 'include' });
	if (!res.ok) throw new Error('Не удалось получить сводку');
	return res.json();
}

export async function fetchRksConsumers(limit = 100, offset = 0): Promise<{ total: number; items: RksConsumer[] }> {
	const res = await fetch(`/api/rks/consumers?limit=${limit}&offset=${offset}`, { credentials: 'include' });
	if (!res.ok) throw new Error('Не удалось получить потребителей');
	return res.json();
}

export async function fetchRksExecution(): Promise<{ rows: RksTask[] }> {
	const res = await fetch('/api/rks/execution', { credentials: 'include' });
	if (!res.ok) throw new Error('Не удалось получить список');
	return res.json();
}

export async function updateRksExecution(fields: {
	task_number: string;
	executor: string | null;
	co_executor: string | null;
	task_report: string | null;
	done_day: string | null;
	violations: string | null;
}): Promise<{ success: boolean; status: string }> {
	const res = await fetch('/api/rks/execution', {
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

export type RksReestrResult = {
	success: boolean;
	reestrs: { name: string; reestr_number: string; count: number }[];
	skipped: number;
	reestr_date: string;
};

export async function createRksReestr(taskNumbers: string[]): Promise<RksReestrResult> {
	const res = await fetch('/api/rks/reestr', {
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

export async function resetRksReestr(taskNumbers: string[]): Promise<{ success: boolean; cleared: number }> {
	const res = await fetch('/api/rks/reestr/reset', {
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

export async function changeRksTaskReport(taskNumber: string, taskReport: string): Promise<{ success: boolean }> {
	const res = await fetch('/api/rks/task-report', {
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

export async function changeRksDueDate(taskNumbers: string[], dueDate: string): Promise<{ success: boolean; updated: number }> {
	const res = await fetch('/api/rks/due-date', {
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

export async function fetchRksOptions(): Promise<RksOptions> {
	const res = await fetch('/api/rks/options', { credentials: 'include' });
	if (!res.ok) throw new Error('Не удалось получить справочники');
	return res.json();
}

export async function fetchObjectPoints(taskNumber: string): Promise<{ points: ObjectPoint[] }> {
	const res = await fetch(`/api/rks/object-points?task_number=${encodeURIComponent(taskNumber)}`, { credentials: 'include' });
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки точек');
	}
	return res.json();
}

export async function addPoint(taskNumber: string, tuId: string): Promise<{ success: boolean; task_number: string }> {
	const res = await fetch('/api/rks/add-point', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ task_number: taskNumber, tu_id: tuId })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка добавления точки');
	}
	return res.json();
}

export async function removeControl(taskNumber: string): Promise<{ success: boolean; deleted: number }> {
	const res = await fetch('/api/rks/remove-control', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ task_number: taskNumber })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка снятия с контроля');
	}
	return res.json();
}

export type EnrollCodeResult = { code: string; expires_at: string; full_name: string };

export async function enrollCode(userId: number): Promise<EnrollCodeResult> {
	const res = await fetch('/api/rks/enroll-code', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ user_id: userId })
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка генерации кода');
	}
	return res.json();
}