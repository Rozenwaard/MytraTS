import { api } from './client';

export interface RleWeek {
	week: number;
	range: string;
}

export interface RleCell {
	count: number;
	per_executor: number;
	per_day: number;
	workers: number;
}

export interface RleRow {
	grid: string;
	values: RleCell[];
}

export interface RleTotal {
	count: number;
	per_executor: number;
	per_day: number;
	executors: number;
}

export interface RleData {
	weeks: RleWeek[];
	grids: string[];
	rows: RleRow[];
	totals: RleTotal[];
}

export async function fetchRle(): Promise<RleData> {
	return api<RleData>('/api/rle');
}

export function rleDownloadUrl(): string {
	return '/api/rle/download';
}
