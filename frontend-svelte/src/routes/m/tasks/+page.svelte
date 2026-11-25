<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { getToken } from '$lib/mobile/auth.svelte';
	import { mobileApi, MobileApiError } from '$lib/mobile/client';
	import { flushQueue } from '$lib/mobile/queue';
	import type { MobileTask, SyncResponse } from '$lib/mobile/types';

	let tasks = $state<MobileTask[]>([]);
	let loading = $state(true);
	let error = $state('');
	let refreshing = $state(false);

	async function load(showSpinner = true) {
		if (showSpinner) loading = true;
		error = '';
		try {
			const data = await mobileApi<SyncResponse>('/api/m/1/sync');
			tasks = data.tasks;
			localStorage.setItem('rks.cache.sync', JSON.stringify(data));
		} catch (err) {
			const cached = localStorage.getItem('rks.cache.sync');
			if (cached) {
				tasks = (JSON.parse(cached) as SyncResponse).tasks;
				error = 'Нет сети — показаны кэшированные задания';
			} else {
				error = err instanceof MobileApiError ? err.message : 'Ошибка загрузки заданий';
			}
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	onMount(() => {
		if (!getToken()) {
			goto('/m/login');
			return;
		}
		load();
		void flushQueue().then(() => load(false));
	});

	async function returnObjectNotFound(tn: string) {
		if (!confirm('Вернуть задание: «Объект не найден»?')) return;
		try {
			await mobileApi('/api/m/1/return', {
				method: 'POST',
				body: JSON.stringify({ task_number: tn, reason: 'Объект не найден' })
			});
			await load(false);
		} catch (err) {
			error = err instanceof MobileApiError ? err.message : 'Ошибка возврата';
		}
	}
</script>

<div class="p-4">
	<div class="mb-4 flex items-center justify-between">
		<h1 class="text-lg font-semibold">Мои задания</h1>
		<button
			onclick={() => {
				refreshing = true;
				load(false);
			}}
			class="text-sm text-primary disabled:opacity-50"
			disabled={refreshing}
		>
			{refreshing ? 'Обновление…' : 'Обновить'}
		</button>
	</div>

	{#if error}
		<p class="mb-3 rounded-md bg-amber-50 p-2 text-sm text-amber-700">{error}</p>
	{/if}

	{#if loading}
		<p class="text-sm text-muted-foreground">Загрузка…</p>
	{:else if tasks.length === 0}
		<p class="text-sm text-muted-foreground">Заданий нет</p>
	{:else}
		<div class="space-y-2">
			{#each tasks as t (t.task_number)}
				<div
					onclick={() => goto(`/m/task/${encodeURIComponent(t.task_number)}`)}
					onkeydown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							e.preventDefault();
							goto(`/m/task/${encodeURIComponent(t.task_number)}`);
						}
					}}
					role="button"
					tabindex="0"
					class="cursor-pointer rounded-lg border bg-card p-3 transition-colors hover:bg-accent"
				>
					<div class="flex items-center justify-between gap-2">
						<span class="text-sm font-semibold">{t.work_type || '—'}</span>
						<span class="text-xs text-muted-foreground">{t.norm} мин</span>
					</div>
					<div class="mt-1 text-sm">{t.subscriber_name || '—'}</div>
					<div class="text-xs text-muted-foreground">{t.address || '—'}</div>
					{#if t.phone}
						<a
							href={`tel:${t.phone.split(/[;,\s]+/)[0].replace(/[^\d+]/g, '')}`}
							onclick={(e) => e.stopPropagation()}
							class="mt-1 inline-block text-sm text-primary underline underline-offset-2"
						>
							{t.phone}
						</a>
					{/if}
					<div class="mt-2 flex items-center justify-between">
						<span class="text-xs text-muted-foreground">{t.meter_serial ? 'ПУ ' + t.meter_serial : ''}</span>
						<span class="text-xs text-muted-foreground">{t.task_number}</span>
					</div>
					<div class="mt-2 border-t pt-2">
						<button
							onclick={(e) => {
								e.stopPropagation();
								returnObjectNotFound(t.task_number);
							}}
							class="text-xs text-destructive underline underline-offset-2"
						>
							Объект не найден
						</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
