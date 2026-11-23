<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
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

	onMount(() => {
		deviceId = getDeviceId();
	});

	async function enroll(e: SubmitEvent) {
		e.preventDefault();
		if (!code.trim()) {
			error = 'Введите код привязки';
			return;
		}
		loading = true;
		error = '';
		try {
			const data = await mobileApi<EnrollResponse>('/api/m/1/enroll', {
				method: 'POST',
				body: JSON.stringify({
					code: code.trim().toUpperCase(),
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
</script>

<div class="flex min-h-screen flex-col justify-center p-6">
	<div class="mb-8 flex items-center justify-center gap-2">
		<Logo />
		<span class="text-lg font-semibold">РКС · мобильный</span>
	</div>

	<form onsubmit={enroll} class="space-y-4">
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
	</form>
</div>
