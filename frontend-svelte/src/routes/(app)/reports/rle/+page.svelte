<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { fetchRle, rleDownloadUrl, type RleData } from '$lib/api/rle';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { auth } from '$lib/store/auth.svelte';

	const RLE_VISIBLE_WEEKS = 5;

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

	const start = $derived(Math.max(0, (data?.weeks.length ?? 0) - RLE_VISIBLE_WEEKS));
	const weeks = $derived((data?.weeks ?? []).slice(start));
	const cards = $derived(data ? computeRleCards(data) : []);

	const fmtNum = (v: number) =>
		v.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

	function handleDownload() {
		const a = document.createElement('a');
		a.href = rleDownloadUrl();
		document.body.appendChild(a);
		a.click();
		a.remove();
	}

	interface RleCard {
		label: string;
		value: number;
		note: string;
		integer?: boolean;
	}

	function computeRleCards(d: RleData): RleCard[] {
		const wks = d.weeks;
		const totals = d.totals;
		if (wks.length === 0) return [];

		let maxExec = { value: -Infinity, week: wks[0].week };
		let minExec = { value: Infinity, week: wks[0].week };
		totals.forEach((t, i) => {
			if (t.executors > maxExec.value) maxExec = { value: t.executors, week: wks[i].week };
			if (t.executors < minExec.value) minExec = { value: t.executors, week: wks[i].week };
		});

		let maxWork = { value: -Infinity, week: wks[0].week };
		let minWork = { value: Infinity, week: wks[0].week };
		totals.forEach((t, i) => {
			if (t.count > maxWork.value) maxWork = { value: t.count, week: wks[i].week };
			if (t.count < minWork.value) minWork = { value: t.count, week: wks[i].week };
		});

		let maxDay = { value: -Infinity, week: wks[0].week, grid: '' };
		let minDay = { value: Infinity, week: wks[0].week, grid: '' };
		d.rows.forEach((row) => {
			row.values.forEach((v, i) => {
				if (v.per_day > maxDay.value) maxDay = { value: v.per_day, week: wks[i].week, grid: row.grid };
				if (v.per_day < minDay.value) minDay = { value: v.per_day, week: wks[i].week, grid: row.grid };
			});
		});

		return [
			{ label: 'Max Работников', value: maxExec.value, note: `Неделя ${maxExec.week}` },
			{ label: 'Min Работников', value: minExec.value, note: `Неделя ${minExec.week}` },
			{ label: 'Max Работ', value: maxWork.value, note: `Неделя ${maxWork.week}`, integer: true },
			{ label: 'Min Работ', value: minWork.value, note: `Неделя ${minWork.week}`, integer: true },
			{ label: 'Max В день', value: maxDay.value, note: `Неделя ${maxDay.week} · ${maxDay.grid}` },
			{ label: 'Min В день', value: minDay.value, note: `Неделя ${minDay.week} · ${minDay.grid}` }
		];
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
				<div class="flex flex-wrap items-start justify-between gap-3 border-b pb-3">
					<div class="flex flex-wrap gap-3">
						{#each cards as c (c.label)}
							<div class="min-w-[130px] rounded-md border border-border bg-card px-3 py-2 shadow-xs">
								<div class="whitespace-nowrap text-xs text-muted-foreground">{c.label}</div>
								<div class="text-lg font-semibold leading-tight tabular-nums">
									{c.integer ? c.value.toLocaleString('ru-RU') : fmtNum(c.value)}
								</div>
								<div class="whitespace-nowrap text-[11px] text-muted-foreground">{c.note}</div>
							</div>
						{/each}
					</div>
					<Button size="sm" variant="outline" onclick={handleDownload}>Скачать</Button>
				</div>

				<div class="overflow-auto rounded-md border">
					<table class="w-full border-collapse text-sm">
						<thead>
							<tr>
								<th class="sticky left-0 z-10 whitespace-nowrap bg-background px-2 py-1 text-left font-semibold">
									Филиал
								</th>
								{#each weeks as w (w.week)}
									<th
										colspan={3}
										class="whitespace-nowrap border-l border-border bg-muted px-2 py-1 text-center font-semibold"
									>
										Неделя {w.week}
										<span class="block text-[10px] font-normal text-muted-foreground">{w.range}</span>
									</th>
								{/each}
							</tr>
							<tr>
								<th class="sticky left-0 z-10 bg-background"></th>
								{#each weeks as w (w.week)}
									<th class="whitespace-nowrap px-2 py-1 text-right font-medium">Работы</th>
									<th class="whitespace-nowrap px-2 py-1 text-right font-medium">Удельно</th>
									<th class="whitespace-nowrap px-2 py-1 text-right font-medium">В день</th>
								{/each}
							</tr>
						</thead>
						<tbody>
							{#each data.rows as row (row.grid)}
								<tr class="border-t border-border">
									<td class="sticky left-0 z-10 whitespace-nowrap bg-background px-2 py-1 font-semibold">
										{row.grid}
									</td>
									{#each row.values.slice(start) as v, i (i)}
										<td class="px-2 py-1 text-right tabular-nums">{v.count.toLocaleString('ru-RU')}</td>
										<td class="px-2 py-1 text-right tabular-nums">{fmtNum(v.per_executor)}</td>
										<td class="px-2 py-1 text-right tabular-nums">{fmtNum(v.per_day)}</td>
									{/each}
								</tr>
							{/each}
							<tr class="border-t border-border">
								<td class="sticky left-0 z-10 whitespace-nowrap bg-background px-2 py-1 font-bold">
									Всего работ
								</td>
								{#each data.totals.slice(start) as t, i (i)}
									<td class="px-2 py-1 text-right font-bold tabular-nums">{t.count.toLocaleString('ru-RU')}</td>
									<td class="px-2 py-1 text-right italic text-muted-foreground">Работников</td>
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

