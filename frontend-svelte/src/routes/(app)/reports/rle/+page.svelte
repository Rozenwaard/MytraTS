<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { fetchRle, rleDownloadUrl, type RleData } from '$lib/api/rle';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { auth } from '$lib/store/auth.svelte';

	const isAdmin = $derived(auth.user?.role === 'администратор');

	const query = createQuery<RleData>(
		toStore(() => ({
			queryKey: ['rle'],
			queryFn: () => fetchRle(),
			enabled: isAdmin
		}))
	);
	const result = fromStore(query);
	const data = $derived(result.current.data);
	const loading = $derived(result.current.isPending);
	const isError = $derived(result.current.isError);

	const weeks = $derived(data?.weeks ?? []);

	const fmtNum = (v: number) =>
		v.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

	function handleDownload() {
		const a = document.createElement('a');
		a.href = rleDownloadUrl();
		document.body.appendChild(a);
		a.click();
		a.remove();
	}
</script>

{#if auth.loading}
	<div class="p-6"><Skeleton class="h-6 w-40" /></div>
{:else if !isAdmin}
	<div class="p-6 text-sm text-muted-foreground">Нет доступа</div>
{:else}
	<div class="flex h-full flex-col gap-3 overflow-auto p-3">
		{#if loading}
			<div class="p-6 text-sm text-muted-foreground">Загружаем…</div>
		{:else if data}
			<div class="flex min-w-0 flex-col gap-3">
				<div class="flex items-center justify-end gap-3 border-b pb-3">
					<Button size="sm" variant="outline" onclick={handleDownload}>Скачать</Button>
				</div>

				<div class="overflow-auto rounded-md border">
					<table class="w-full border-collapse text-sm">
						<thead>
							<tr>
								<th class="sticky left-0 z-10 bg-background"></th>
								{#each weeks as w (w.week)}
									<th
										colspan={4}
										class="whitespace-nowrap border-l border-border bg-muted px-2 py-1 text-center font-semibold"
									>
										Неделя {w.week}
										<span class="block text-[10px] font-normal text-muted-foreground">{w.range}</span>
									</th>
								{/each}
							</tr>
							<tr>
								<th class="sticky left-0 z-10 whitespace-nowrap bg-background px-2 py-1 text-left font-semibold">
									Филиал
								</th>
								{#each weeks as w (w.week)}
									<th class="whitespace-nowrap px-2 py-1 text-right font-medium">Работы</th>
									<th class="whitespace-nowrap px-2 py-1 text-right font-medium">Удельно</th>
									<th class="whitespace-nowrap px-2 py-1 text-right font-medium">В день</th>
									<th class="whitespace-nowrap px-2 py-1 text-right font-medium">Работники</th>
								{/each}
							</tr>
						</thead>
						<tbody>
							{#each data.rows as row (row.grid)}
								<tr class="border-t border-border">
									<td class="sticky left-0 z-10 whitespace-nowrap bg-background px-2 py-1 font-semibold">
										{row.grid}
									</td>
									{#each row.values as v, i (i)}
										<td class="px-2 py-1 text-right tabular-nums">{v.count.toLocaleString('ru-RU')}</td>
										<td class="px-2 py-1 text-right tabular-nums">{fmtNum(v.per_executor)}</td>
										<td class="px-2 py-1 text-right tabular-nums">{fmtNum(v.per_day)}</td>
										<td class="px-2 py-1 text-right tabular-nums">{fmtNum(v.workers)}</td>
									{/each}
								</tr>
							{/each}
							<tr class="border-t border-border">
								<td class="sticky left-0 z-10 whitespace-nowrap bg-background px-2 py-1 font-bold">
									Всего
								</td>
								{#each data.totals as t, i (i)}
									<td class="px-2 py-1 text-right font-bold tabular-nums">{t.count.toLocaleString('ru-RU')}</td>
									<td class="px-2 py-1 text-right font-bold tabular-nums">{fmtNum(t.per_executor)}</td>
									<td class="px-2 py-1 text-right font-bold tabular-nums">{fmtNum(t.per_day)}</td>
									<td class="px-2 py-1 text-right font-bold tabular-nums">{fmtNum(t.executors)}</td>
								{/each}
							</tr>
						</tbody>
					</table>
				</div>
			</div>
		{:else if isError}
			<div class="p-6 text-sm text-muted-foreground">Ошибка загрузки РЛЭ</div>
		{:else}
			<div class="p-6 text-sm text-muted-foreground">Нет данных</div>
		{/if}
	</div>
{/if}
