import { registerPlugin } from '@capacitor/core';

export interface CameraStreamResult {
    dataUrl?: string;
    cancelled?: boolean;
}

export interface CameraStreamPlugin {
    start(options: { skirtText: string; lat: number; lng: number }): Promise<CameraStreamResult>;
    stop(): Promise<void>;
}

export const CameraStream = registerPlugin<CameraStreamPlugin>('CameraStream');

export function dataUrlToBlob(dataUrl: string): Blob {
    const comma = dataUrl.indexOf(',');
    const meta = dataUrl.slice(0, comma);
    const b64 = dataUrl.slice(comma + 1);
    const mime = /data:([^;]+);base64/.exec(meta)?.[1] ?? 'image/jpeg';
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes.buffer], { type: mime });
}
