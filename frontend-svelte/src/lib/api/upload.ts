export type UploadProgress = {
	status:
		| 'starting'
		| 'loading'
		| 'loaded'
		| 'processing'
		| 'merging'
		| 'complete'
		| 'error';
	progress: number;
	total?: number;
	loaded?: number;
	inserted?: number;
	updated?: number;
	message?: string;
};

/**
 * Загрузка .xlsx в raw_afl. Отдельный fetch (не через api<T>()):
 * multipart требует, чтобы браузер сам выставил Content-Type с boundary.
 */
export async function uploadXlsx(file: File): Promise<{ upload_id: string }> {
	const form = new FormData();
	form.append('data', file);
	const res = await fetch('/api/upload', {
		method: 'POST',
		credentials: 'include',
		body: form
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки');
	}
	return (await res.json()) as { upload_id: string };
}

export async function fetchUploadProgress(uploadId: string): Promise<UploadProgress> {
	const res = await fetch(`/api/upload/progress/${uploadId}`, { credentials: 'include' });
	if (!res.ok) {
		throw new Error('Не удалось получить прогресс загрузки');
	}
	return (await res.json()) as UploadProgress;
}

/**
 * Скачивает номера заданий «в работе» (.txt, task_number столбиком).
 */
export async function downloadTaskNumbersInWork(): Promise<void> {
	const res = await fetch('/api/upload/task-numbers-in-work', { credentials: 'include' });
	if (!res.ok) {
		throw new Error('Не удалось получить номера заданий');
	}
	const blob = await res.blob();
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	const cd = res.headers.get('Content-Disposition') ?? '';
	const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
	a.download = m ? decodeURIComponent(m[1]) : 'номера_заданий_в_работе.txt';
	document.body.appendChild(a);
	a.click();
	a.remove();
	URL.revokeObjectURL(url);
}
