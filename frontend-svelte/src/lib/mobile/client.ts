import { Capacitor, CapacitorHttp } from '@capacitor/core';
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
const BASE = import.meta.env.VITE_API_URL ?? import.meta.env.PUBLIC_API_URL ?? '';

type RawResponse = { status: number; text: string };

async function rawRequest(url: string, init?: RequestInit): Promise<RawResponse> {
	if (Capacitor.isNativePlatform()) {
		// Нативный HTTP (OkHttp) — обходит CORS и WebView-сетку (лечит «Failed to fetch»).
		const res = await CapacitorHttp.request({
			method: (init?.method ?? 'GET') as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
			url,
			headers: init?.headers as Record<string, string> | undefined,
			data: init?.body as string | undefined,
			connectTimeout: 15000,
			readTimeout: 30000
		});
		const text = typeof res.data === 'string' ? res.data : JSON.stringify(res.data);
		return { status: res.status, text };
	}
	const res = await fetch(url, init);
	const text = await res.text().catch(() => '');
	return { status: res.status, text };
}

export async function mobileApi<T>(path: string, init?: RequestInit): Promise<T> {
	const token = getToken();
	const url = `${BASE}${path}`;
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(token ? { Authorization: `Bearer ${token}` } : {}),
		...(init?.headers as Record<string, string> | undefined)
	};

	let status: number;
	let text: string;
	try {
		const raw = await rawRequest(url, { ...init, headers });
		status = raw.status;
		text = raw.text;
	} catch (e) {
		throw new Error(
			`Сеть недоступна для ${url} — ${e instanceof Error ? e.message : String(e)}. Проверьте интернет на телефоне.`
		);
	}

	if (status >= 400) {
		let message = `HTTP ${status}`;
		try {
			const j = JSON.parse(text);
			if (j?.error) message = j.error;
		} catch {
			/* не JSON */
		}
		throw new MobileApiError(status, `${message} (url=${url})`);
	}
	if (status === 204) return undefined as T;
	try {
		return JSON.parse(text) as T;
	} catch {
		throw new Error(`Не-JSON ответ. url=${url} HTTP=${status} Ответ=${text.slice(0, 160)}`);
	}
}
