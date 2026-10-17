export type WorkTypeOption = { short: string; title: string; customer: string | null };
export type UlrOptions = { customers: string[]; grids: string[]; work_types: WorkTypeOption[] };

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
	fields: { customer: string; visit_reason: string; work_type_in_task: string; grid: string; due_date: string },
	file: File
): Promise<UlrUploadResult> {
	const form = new FormData();
	form.append('customer', fields.customer);
	form.append('visit_reason', fields.visit_reason);
	form.append('work_type_in_task', fields.work_type_in_task);
	form.append('grid', fields.grid);
	form.append('due_date', fields.due_date);
	form.append('file', file);

	const res = await fetch('/api/ulr/upload', { method: 'POST', credentials: 'include', body: form });
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки');
	}
	return res.json();
}
