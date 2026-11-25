<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount, tick } from 'svelte';
	import { Html5Qrcode } from 'html5-qrcode';
	import { Capacitor } from '@capacitor/core';
	import { BarcodeScanner } from '@capacitor-mlkit/barcode-scanning';
	import { getDeviceId, setMobileAuth } from '$lib/mobile/auth.svelte';
	import { mobileApi, MobileApiError } from '$lib/mobile/client';
	import type { EnrollResponse } from '$lib/mobile/types';
	import { Button } from '$lib/components/ui/button';
	import Logo from '$lib/components/logo.svelte';

	let deviceId = $state('');
	let error = $state('');
	let debug = $state('');
	let loading = $state(false);
	let scanning = $state(false);
	let nativeScan = $state(false);
	let scanner: Html5Qrcode | null = null;

	onMount(() => {
		deviceId = getDeviceId();
	});

	function extractCode(qrText: string): string {
		let c = qrText.trim();
		try {
			const u = new URL(c);
			const p = u.searchParams.get('code');
			if (p) c = p;
		} catch {
			/* не URL — значит просто код */
		}
		return c.trim().toUpperCase();
	}

	async function doEnroll(codeValue: string) {
		loading = true;
		error = '';
		const code = extractCode(codeValue);
		debug = 'Сканер видит: ' + JSON.stringify(codeValue)
			+ '\nИзвлечённый код: ' + code
			+ '\nAPI-база: ' + ((import.meta.env.VITE_API_URL ?? import.meta.env.PUBLIC_API_URL) ?? '(пусто)')
			+ '\ndevice_id: ' + deviceId;
		try {
			const data = await mobileApi<EnrollResponse>('/api/m/1/enroll', {
				method: 'POST',
				body: JSON.stringify({
					code,
					device_id: deviceId,
					platform: Capacitor.isNativePlatform() ? 'android' : 'web'
				})
			});
			setMobileAuth(data.token, data.user.full_name);
			await goto('/m/tasks');
		} catch (err) {
			const detail = err instanceof MobileApiError
				? `${err.message} (HTTP ${err.status})`
				: err instanceof Error ? err.message : String(err);
			error = 'Ошибка привязки: ' + detail;
		} finally {
			loading = false;
		}
	}

	async function startScan() {
		scanning = true;
		error = '';
		if (Capacitor.isNativePlatform()) {
			await startNativeScan();
		} else {
			await startWebScan();
		}
	}

	async function startNativeScan() {
		nativeScan = true;
		document.body.classList.add('barcode-scanner-active');
		document.documentElement.classList.add('barcode-scanner-active');
		try {
			const { supported } = await BarcodeScanner.isSupported();
			if (!supported) {
				error = 'Сканер не поддерживается на этом устройстве';
				await stopScan();
				return;
			}
			const { camera } = await BarcodeScanner.requestPermissions();
			if (!camera) {
				error = 'Нет доступа к камере';
				await stopScan();
				return;
			}
			await BarcodeScanner.addListener('barcodesScanned', async (result: any) => {
				const raw = result?.barcodes?.[0]?.rawValue;
				if (raw) {
					await onScan(raw);
				}
			});
			await BarcodeScanner.startScan();
		} catch (e) {
			error = 'Не удалось открыть камеру: ' + (e instanceof Error ? e.message : String(e));
			await stopScan();
		}
	}

	async function startWebScan() {
		await tick();
		try {
			scanner = new Html5Qrcode('qr-reader');
			await scanner.start(
				{ facingMode: 'environment' },
				{ fps: 10, qrbox: { width: 250, height: 250 } },
				(qrText) => {
					void onScan(qrText);
				},
				() => {}
			);
		} catch (e) {
			error = 'Не удалось открыть камеру: ' + (e instanceof Error ? e.message : String(e));
			await stopScan();
		}
	}

	async function onScan(qrText: string) {
		debug = 'Сканер видит: ' + JSON.stringify(qrText);
		await stopScan();
		await doEnroll(qrText);
	}

	async function stopScan() {
		if (nativeScan) {
			try {
				await BarcodeScanner.removeAllListeners();
				await BarcodeScanner.stopScan();
			} catch {
				/* уже остановлен */
			}
			document.body.classList.remove('barcode-scanner-active');
			document.documentElement.classList.remove('barcode-scanner-active');
			nativeScan = false;
		}
		if (scanner) {
			try {
				await scanner.stop();
				scanner.clear();
			} catch {
				/* уже остановлен */
			}
			scanner = null;
		}
		scanning = false;
	}
</script>

<style>
	:global(html.barcode-scanner-active),
	:global(body.barcode-scanner-active) {
		visibility: hidden;
		background: transparent !important;
	}
	:global(.barcode-scanner-modal) {
		visibility: visible !important;
	}
</style>

<div class="flex min-h-screen flex-col items-center justify-center p-6">
	<div class="mb-12 flex items-center gap-3">
		<Logo />
		<span class="text-3xl font-semibold tracking-tight">MytraGo</span>
	</div>

	<Button class="w-full max-w-sm py-6 text-lg" onclick={startScan} disabled={scanning || loading}>
		{loading ? 'Привязка…' : 'Сканировать QR-код'}
	</Button>

	<p class="mt-4 text-xs text-muted-foreground">Наведите камеру на QR-код, выданный в бэкофисе</p>

	{#if error}
		<p class="mt-4 max-w-sm text-center text-sm text-destructive">{error}</p>
	{/if}

	{#if debug}
		<pre class="mt-4 w-full max-w-sm whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-left text-xs">{debug}</pre>
	{/if}
</div>

{#if scanning && !nativeScan}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4">
		<div class="w-full max-w-sm">
			<div id="qr-reader" class="overflow-hidden rounded-lg" style="min-height: 320px"></div>
			<Button variant="outline" class="mt-3 w-full" onclick={stopScan}>Отмена</Button>
		</div>
	</div>
{/if}

{#if nativeScan}
	<div class="barcode-scanner-modal fixed inset-0 z-50 flex items-end justify-center p-4">
		<Button class="mb-8 bg-black/70" onclick={stopScan}>Отмена</Button>
	</div>
{/if}
