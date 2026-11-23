import { getToken } from './auth.svelte';

export class MobileApiError extends Error {
	status: number;
	constructor(status: number, message: string) {
		super(message);
		this.status = status;
	}
}

// База для запросов. Web-PWA: оставляем '' → относительные /api/* (Vite-proxy / same-origin).
// Capacitor: собираем с PUBLIC_API_URL=https://домен.ru (абсолютный URL бэка).
const BASE = import.meta.env.PUBLIC_API_URL ?? '';

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
