<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount, tick } from 'svelte';
	import { Html5Qrcode } from 'html5-qrcode';
	import { getDeviceId, setMobileAuth } from '$lib/mobile/auth.svelte';
	import { mobileApi, MobileApiError } from '$lib/mobile/client';
	import type { EnrollResponse } from '$lib/mobile/types';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import Logo from '$lib/components/logo.svelte';

	let code = $state('');
	let deviceId = $state('');
	let error = $state('');
	let loading = $state(false);
	let scanning = $state(false);
	let scanner: Html5Qrcode | null = null;

	onMount(() => {
		deviceId = getDeviceId();
	});

	async function doEnroll(codeValue: string) {
		if (!codeValue.trim()) {
			error = 'Введите код привязки';
			return;
		}
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

	function onSubmit(e: SubmitEvent) {
		e.preventDefault();
		void doEnroll(code);
	}

	async function startScan() {
		scanning = true;
		error = '';
		await tick();
		scanner = new Html5Qrcode('qr-reader');
		try {
			await scanner.start(
				{ facingMode: 'environment' },
				{ fps: 10, qrbox: { width: 250, height: 250 } },
				(qrText) => {
					void onScan(qrText);
				},
				() => {}
			);
		} catch {
			error = 'Не удалось открыть камеру. Проверьте доступ к камере.';
			stopScan();
		}
	}

	async function onScan(qrText: string) {
		const c = qrText.trim().toUpperCase();
		await stopScan();
		code = c;
		await doEnroll(c);
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

<div class="flex min-h-screen flex-col justify-center p-6">
	<div class="mb-8 flex items-center justify-center gap-2">
		<Logo />
		<span class="text-lg font-semibold">РКС · мобильный</span>
	</div>

	<form onsubmit={onSubmit} class="space-y-4">
		<div class="space-y-1.5">
			<label class="text-sm font-medium" for="code">Код привязки</label>
			<Input
				id="code"
				placeholder="Например, A1B2C3"
				bind:value={code}
				autocomplete="off"
			/>
		</div>

		<p class="text-xs text-muted-foreground">Устройство: {deviceId}</p>

		{#if error}
			<p class="text-sm text-destructive">{error}</p>
		{/if}

		<Button type="submit" class="w-full" disabled={loading}>
			{loading ? 'Привязка…' : 'Привязать устройство'}
		</Button>
		<Button type="button" variant="outline" class="w-full" onclick={startScan} disabled={loading}>
			Сканировать QR
		</Button>
	</form>
</div>

{#if scanning}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
		<div class="w-full max-w-sm">
			<div id="qr-reader" class="overflow-hidden rounded-lg"></div>
			<Button variant="outline" class="mt-3 w-full" onclick={stopScan}>Отмена</Button>
		</div>
	</div>
{/if}
