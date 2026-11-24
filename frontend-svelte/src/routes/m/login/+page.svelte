<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount, tick } from 'svelte';
	import { Html5Qrcode } from 'html5-qrcode';
	import { getDeviceId, setMobileAuth } from '$lib/mobile/auth.svelte';
	import { mobileApi, MobileApiError } from '$lib/mobile/client';
	import type { EnrollResponse } from '$lib/mobile/types';
	import { Button } from '$lib/components/ui/button';
	import Logo from '$lib/components/logo.svelte';

	let deviceId = $state('');
	let error = $state('');
	let loading = $state(false);
	let scanning = $state(false);
	let scanner: Html5Qrcode | null = null;

	onMount(() => {
		deviceId = getDeviceId();
	});

	async function doEnroll(codeValue: string) {
		loading = true;
		error = '';
		try {
			const data = await mobileApi<EnrollResponse>('/api/m/1/enroll', {
				method: 'POST',
				body: JSON.stringify({
					code: codeValue.trim().toUpperCase(),
					device_id: deviceId,
					platform: 'web'
				})
			});
			setMobileAuth(data.token, data.user.full_name);
			await goto('/m/tasks');
		} catch (err) {
			error = err instanceof MobileApiError ? err.message : 'Ошибка привязки';
		} finally {
			loading = false;
		}
	}

	async function startScan() {
		scanning = true;
		error = '';
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
		let c = qrText.trim();
		try {
			const u = new URL(c);
			const p = u.searchParams.get('code');
			if (p) c = p;
		} catch {
			/* не URL — значит просто код */
		}
		await stopScan();
		await doEnroll(c.toUpperCase());
	}

	async function stopScan() {
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
</div>

{#if scanning}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4">
		<div class="w-full max-w-sm">
			<div id="qr-reader" class="overflow-hidden rounded-lg" style="min-height: 320px"></div>
			<Button variant="outline" class="mt-3 w-full" onclick={stopScan}>Отмена</Button>
		</div>
	</div>
{/if}
