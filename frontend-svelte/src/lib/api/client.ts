const BASE = '';

export class ApiError extends Error {
	status: number;
	constructor(status: number, message: string) {
		super(message);
		this.status = status;
	}
}

let onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(handler: (() => void) | null): void {
	onUnauthorized = handler;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		...init,
		headers: {
			'Content-Type': 'application/json',
			...init?.headers
		},
		credentials: 'include'
	});
	if (!res.ok) {
		if (res.status === 401) {
			onUnauthorized?.();
		}
		const body = await res.json().catch(() => ({}));
		throw new ApiError(res.status, body.error ?? res.statusText);
	}
	if (res.headers.get('content-type')?.includes('application/json')) {
		return res.json();
	}
	return undefined as T;
}

export interface User {
	id: number;
	full_name: string;
	dept: string;
	locale: string | null;
	position: string;
	staff_id: string;
	role: 'администратор' | 'специалист' | 'менеджер' | 'оператор' | 'работник';
}
