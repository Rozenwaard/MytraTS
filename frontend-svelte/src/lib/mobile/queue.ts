import { getToken } from './auth.svelte';
import { mobileApi, MobileApiError } from './client';

// Офлайн-очередь (IndexedDB): неотправленные отчёты и фото, повтор при reconnect.

const DB_NAME = 'rks-offline';
const DB_VERSION = 1;

function openDb(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const req = indexedDB.open(DB_NAME, DB_VERSION);
		req.onupgradeneeded = () => {
			const db = req.result;
			if (!db.objectStoreNames.contains('reports')) db.createObjectStore('reports', { keyPath: 'id', autoIncrement: true });
			if (!db.objectStoreNames.contains('photos')) db.createObjectStore('photos', { keyPath: 'id', autoIncrement: true });
		};
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
}

function txPut(store: string, value: Record<string, unknown>): Promise<void> {
	return openDb().then(
		(db) =>
			new Promise<void>((resolve, reject) => {
				const tx = db.transaction(store, 'readwrite');
				tx.objectStore(store).add(value);
				tx.oncomplete = () => {
					db.close();
					resolve();
				};
				tx.onerror = () => {
					db.close();
					reject(tx.error);
				};
			})
	);
}

function txAll<T>(store: string): Promise<T[]> {
	return openDb().then(
		(db) =>
			new Promise<T[]>((resolve, reject) => {
				const tx = db.transaction(store, 'readonly');
				const req = tx.objectStore(store).getAll();
				req.onsuccess = () => {
					db.close();
					resolve((req.result ?? []) as T[]);
				};
				req.onerror = () => {
					db.close();
					reject(req.error);
				};
			})
	);
}

function txDelete(store: string, id: number): Promise<void> {
	return openDb().then(
		(db) =>
			new Promise<void>((resolve, reject) => {
				const tx = db.transaction(store, 'readwrite');
				tx.objectStore(store).delete(id);
				tx.oncomplete = () => {
					db.close();
					resolve();
				};
				tx.onerror = () => {
					db.close();
					reject(tx.error);
				};
			})
	);
}

interface QueuedReport {
	id?: number;
	payload: Record<string, unknown>;
	queuedAt: string;
}
interface QueuedPhoto {
	id?: number;
	client_op_id: string;
	task_number: string;
	photo_type?: string;
	blob: Blob;
	queuedAt: string;
}

export async function enqueueReport(payload: Record<string, unknown>): Promise<void> {
	await txPut('reports', { payload, queuedAt: new Date().toISOString() });
}

export async function enqueuePhoto(op: { client_op_id: string; task_number: string; blob: Blob; photo_type?: string }): Promise<void> {
	await txPut('photos', { ...op, queuedAt: new Date().toISOString() });
}

export async function queueCount(): Promise<{ reports: number; photos: number }> {
	const [r, p] = await Promise.all([txAll<QueuedReport>('reports'), txAll<QueuedPhoto>('photos')]);
	return { reports: r.length, photos: p.length };
}

async function authHeaders(): Promise<Record<string, string>> {
	const token = getToken();
	return token ? { Authorization: `Bearer ${token}` } : {};
}

// Пытается отправить всё накопленное. Возвращает число успешно отправленных.
export async function flushQueue(): Promise<{ reports: number; photos: number }> {
	const reports = await txAll<QueuedReport>('reports');
	let rs = 0;
	for (const r of reports) {
		if (r.id == null) continue;
		try {
			await mobileApi('/api/m/1/reports', { method: 'POST', body: JSON.stringify(r.payload) });
			await txDelete('reports', r.id);
			rs++;
		} catch (e) {
			// Закрытое/переданное задание — дропаем; сетевая ошибка — оставляем на повтор.
			if (e instanceof MobileApiError && e.closed) {
				await txDelete('reports', r.id);
			}
		}
	}

	const photos = await txAll<QueuedPhoto>('photos');
	let ps = 0;
	for (const p of photos) {
		if (p.id == null) continue;
		try {
			const form = new FormData();
			form.append('client_op_id', p.client_op_id);
			form.append('task_number', p.task_number);
			form.append('photo_type', p.photo_type ?? 'general');
			form.append('file', p.blob, 'photo.webp');
			const res = await fetch('/api/m/1/photos', {
				method: 'POST',
				headers: await authHeaders(),
				body: form
			});
			if (res.ok) {
				await txDelete('photos', p.id);
				ps++;
			}
		} catch {
			/* офлайн — оставляем */
		}
	}

	return { reports: rs, photos: ps };
}

// Автоповтор при появлении сети.
export function setupAutoFlush(): void {
	if (typeof window === 'undefined') return;
	window.addEventListener('online', () => {
		void flushQueue();
	});
}
