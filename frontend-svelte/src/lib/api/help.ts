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
