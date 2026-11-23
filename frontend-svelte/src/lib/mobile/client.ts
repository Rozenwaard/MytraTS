import { getToken } from './auth.svelte';

export class MobileApiError extends Error {
	status: number;
	constructor(status: number, message: string) {
		super(message);
		this.status = status;
	}
}

// База для нативных запросов (Capacitor): в проде указать URL бэка. В dev — через proxy vite.
const BASE = '';

export async function mobileApi<T>(path: string, init?: RequestInit): Promise<T> {
	const token = getToken();
	const res = await fetch(`${BASE}${path}`, {
		...init,
		headers: {
			'Content-Type': 'application/json',
			...(token ? { Authorization: `Bearer ${token}` } : {}),
			...init?.headers
		}
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new MobileApiError(res.status, body.error ?? res.statusText);
	}
	if (res.status === 204) return undefined as T;
	return res.json();
}
