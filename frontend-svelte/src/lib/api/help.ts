import { api } from './client';

export interface HelpBlock {
	type: 'p' | 'table' | 'h';
	text?: string;
	rows?: string[][];
	menu?: string;
}

export interface HelpPageData {
	key: string;
	title: string;
	updated_at: string | null;
	blocks: HelpBlock[];
}

export async function fetchHelpPage(key: string): Promise<HelpPageData> {
	return api<HelpPageData>(`/api/help/${key}`);
}

export async function uploadHelpDocx(key: string, file: File): Promise<{ success: boolean }> {
	const form = new FormData();
	form.append('data', file);
	const res = await fetch(`/api/help/${key}`, {
		method: 'POST',
		credentials: 'include',
		body: form
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки');
	}
	return (await res.json()) as { success: boolean };
}
