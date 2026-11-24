<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getDeviceId, setMobileAuth } from '$lib/mobile/auth.svelte';
	import { mobileApi, MobileApiError } from '$lib/mobile/client';
	import type { EnrollResponse } from '$lib/mobile/types';

	const code = $derived(page.url.searchParams.get('code') ?? '');
	let error = $state('');

	onMount(async () => {
		if (!code) {
			error = 'В ссылке нет кода привязки';
			return;
		}
		try {
			const data = await mobileApi<EnrollResponse>('/api/m/1/enroll', {
				method: 'POST',
				body: JSON.stringify({
					code: code.trim().toUpperCase(),
					device_id: getDeviceId(),
					platform: 'web'
				})
			});
			setMobileAuth(data.token, data.user.full_name);
			await goto('/m/tasks');
		} catch (err) {
			error = err instanceof MobileApiError ? err.message : 'Ошибка привязки';
		}
	});
</script>

<div class="flex min-h-screen flex-col items-center justify-center p-6">
	{#if error}
		<p class="max-w-sm text-center text-sm text-destructive">{error}</p>
	{:else}
		<p class="text-sm text-muted-foreground">Привязка устройства…</p>
	{/if}
</div>