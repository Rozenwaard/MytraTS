import { getToken } from './auth.svelte';
import { enqueuePhoto } from './queue';

export interface TakenPhoto {
	sha256: string;
	url: string; // локальный objectURL для превью
}

// Захват фото → сжатие в WebP (~1600×1200) → загрузка на бэк.
export async function takePhoto(clientOpId: string, taskNumber: string): Promise<TakenPhoto | null> {
	const file = await pickPhoto();
	if (!file) return null;
	const webp = await compressToWebp(file);
	const url = URL.createObjectURL(webp);
	try {
		const { sha256 } = await uploadPhoto(clientOpId, taskNumber, webp);
		return { sha256, url };
	} catch {
		await enqueuePhoto({ client_op_id: clientOpId, task_number: taskNumber, blob: webp });
		return { sha256: 'pending', url };
	}
}

function pickPhoto(): Promise<Blob | null> {
	return new Promise((resolve) => {
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = 'image/*';
		input.setAttribute('capture', 'environment');
		input.onchange = () => resolve(input.files?.[0] ?? null);
		input.oncancel = () => resolve(null);
		input.click();
	});
}

function compressToWebp(blob: Blob, maxW = 1600, maxH = 1200, quality = 0.75): Promise<Blob> {
	return new Promise((resolve) => {
		const url = URL.createObjectURL(blob);
		const img = new Image();
		img.onload = () => {
			const scale = Math.min(1, maxW / img.width, maxH / img.height);
			const w = Math.max(1, Math.round(img.width * scale));
			const h = Math.max(1, Math.round(img.height * scale));
			const canvas = document.createElement('canvas');
			canvas.width = w;
			canvas.height = h;
			const ctx = canvas.getContext('2d')!;
			ctx.drawImage(img, 0, 0, w, h);
			URL.revokeObjectURL(url);
			canvas.toBlob((out) => resolve(out ?? blob), 'image/webp', quality);
		};
		img.onerror = () => {
			URL.revokeObjectURL(url);
			resolve(blob);
		};
		img.src = url;
	});
}

async function uploadPhoto(clientOpId: string, taskNumber: string, blob: Blob): Promise<{ sha256: string }> {
	const form = new FormData();
	form.append('client_op_id', clientOpId);
	form.append('task_number', taskNumber);
	form.append('file', blob, 'photo.webp');
	const token = getToken();
	const res = await fetch('/api/m/1/photos', {
		method: 'POST',
		headers: token ? { Authorization: `Bearer ${token}` } : {},
		body: form
	});
	if (!res.ok) {
		const body = (await res.json().catch(() => ({}))) as { error?: string };
		throw new Error(body.error ?? 'Ошибка загрузки фото');
	}
	return res.json();
}
