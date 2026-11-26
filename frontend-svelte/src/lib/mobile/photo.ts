import { Capacitor } from '@capacitor/core';
import { getToken, mobileAuth } from './auth.svelte';
import { enqueuePhoto } from './queue';
import { CameraStream, dataUrlToBlob } from './camera';
import type { GeoResult } from './geo';

export interface TakenPhoto {
	sha256: string;
	url: string; // локальный objectURL для превью
}

export interface PhotoContext {
	energy_object_code?: string | null;
	contract_number?: string | null;
}

// Захват фото → (нативно уже ресайз 1600px + «юбка» + EXIF) → загрузка на бэк.
export async function takePhoto(
	clientOpId: string,
	taskNumber: string,
	ctx: PhotoContext | null,
	geo: GeoResult | null,
	photoType = 'general'
): Promise<TakenPhoto | null> {
	const skirtText = buildSkirtText(taskNumber, ctx, geo);
	let blob: Blob | null;
	if (Capacitor.isNativePlatform()) {
		const res = await CameraStream.start({ skirtText, lat: geo?.lat ?? 0, lng: geo?.lng ?? 0 });
		if (!res || res.cancelled) return null;
		blob = dataUrlToBlob(res.dataUrl ?? '');
	} else {
		const file = await pickPhoto();
		if (!file) return null;
		blob = await compressToWebp(file);
	}

	const url = URL.createObjectURL(blob);
	try {
		const { sha256 } = await uploadPhoto(clientOpId, taskNumber, blob, photoType);
		return { sha256, url };
	} catch {
		await enqueuePhoto({ client_op_id: clientOpId, task_number: taskNumber, blob, photo_type: photoType });
		return { sha256: 'pending', url };
	}
}

// Текст «юбки»: дата/время · координаты · № задания · ЭО (код энергообъекта).
export function buildSkirtText(taskNumber: string, ctx: PhotoContext | null, geo: GeoResult | null): string {
	const now = new Date();
	const pad = (n: number) => String(n).padStart(2, '0');
	const ts = `${pad(now.getDate())}.${pad(now.getMonth() + 1)}.${now.getFullYear()} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
	const coord = geo ? `${geo.lat.toFixed(6)}, ${geo.lng.toFixed(6)}` : '—';
	const eo = ctx?.energy_object_code ?? ctx?.contract_number ?? '—';
	const name = mobileAuth.fullName ?? '—';
	return `${name} · ${ts} · ${coord} · № ${taskNumber} · ЭО ${eo}`;
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

async function uploadPhoto(clientOpId: string, taskNumber: string, blob: Blob, photoType: string): Promise<{ sha256: string }> {
	const form = new FormData();
	form.append('client_op_id', clientOpId);
	form.append('task_number', taskNumber);
	form.append('photo_type', photoType);
	const ext = blob.type === 'image/webp' ? 'webp' : 'jpg';
	form.append('file', blob, `photo.${ext}`);
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
