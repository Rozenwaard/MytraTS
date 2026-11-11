<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import {
		fetchRle,
		fetchReadingsRegister,
		uploadRle,
		fetchRlePeriods,
		downloadExecutionReport,
		type RleData,
		type RlePeriod
	} from '$lib/api/rle';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { auth } from '$lib/store/auth.svelte';

	const MONTHS = [
		'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
		'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
	];

	const isAdmin = $derived(auth.user?.role === 'администратор');

	const periodsQuery = createQuery<{ periods: RlePeriod[]; default: string }>(
		toStore(() => ({
			queryKey: ['rle-periods'],
			queryFn: () => fetchRlePeriods(),
			enabled: isAdmin
		}))
	);
	const periodsResult = fromStore(periodsQuery);

	let periods = $state<RlePeriod[]>([]);
	let selected = $state<Set<string>>(new Set());

	$effect(() => {
		const d = periodsResult.current.data;
		if (!d) return;
		periods = d.periods;
		if (selected.size === 0) {
			const def = d.periods.some((p) => p.value === d.default)
				? d.default
				: d.periods[0]?.value ?? '';
			if (def) selected = new Set([def]);
		}
	});

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

	let uploading = $state(false);
	let uploadError = $state('');
	let downloading = $state(false);
	let downloadError = $state('');
	let reporting = $state(false);
	let reportError = $state('');
	let fileInput = $state<HTMLInputElement | undefined>(undefined);

	function openPicker() {
		if (fileInput) {
			fileInput.value = '';
			fileInput.click();
		}
	}

	function onFileChange(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (file) handleUpload(file);
	}

	async function handleUpload(file: File) {
		uploading = true;
		uploadError = '';
		try {
			const { blob, filename } = await uploadRle(file);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch (e) {
			uploadError = e instanceof Error ? e.message : 'Ошибка загрузки 1С';
		} finally {
			uploading = false;
		}
	}

	async function downloadReadings() {
		downloading = true;
		downloadError = '';
		try {
			const { blob, filename } = await fetchReadingsRegister();
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch (e) {
			downloadError = e instanceof Error ? e.message : 'Ошибка выгрузки «Реестр показаний»';
		} finally {
			downloading = false;
		}
	}

	async function downloadReport() {
		reporting = true;
		reportError = '';
		try {
			const { blob, filename } = await downloadExecutionReport([...selected]);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch (e) {
			reportError = e instanceof Error ? e.message : 'Ошибка выгрузки «Отчёт о выполнении»';
		} finally {
			reporting = false;
		}
	}

	function togglePeriod(value: string) {
		const next = new Set(selected);
		if (next.has(value)) next.delete(value);
		else next.add(value);
		selected = next;
	}

	function tileClass(p: RlePeriod): string {
		const base = 'w-full rounded-md border px-3 py-2 text-left transition-colors';
		if (selected.has(p.value)) {
			return `${base} border-primary bg-primary/10`;
		}
		return `${base} border-input bg-background hover:bg-muted`;
	}
</script>

{#if auth.loading}
	<div class="p-6"><Skeleton class="h-6 w-40" /></div>
{:else if !isAdmin}
	<div class="p-6 text-sm text-muted-foreground">Нет доступа</div>
{:else}
	<div class="flex h-full overflow-hidden">
		<div class="w-44 shrink-0 space-y-2 overflow-auto border-r p-3">
			{#each periods as p (p.value)}
				<button
					type="button"
					class={tileClass(p)}
					onclick={() => togglePeriod(p.value)}
				>
					<div class="text-base font-semibold">{MONTHS[Number(p.value.split('-')[1]) - 1]}</div>
					<div class="text-xs text-muted-foreground">
						{p.value.split('-')[0]}{p.is_archived ? ' · архив' : ''}
					</div>
				</button>
			{/each}
		</div>

		<div class="flex min-w-0 flex-1 flex-col gap-3 overflow-auto p-3">
			{#if loading}
			<div class="p-6 text-sm text-muted-foreground">Загружаем…</div>
		{:else if data}
			<div class="flex min-w-0 flex-col gap-3">
				<div class="flex items-center justify-end gap-3 border-b pb-3">
					<input
						bind:this={fileInput}
						type="file"
						accept=".xlsx,.xls"
						class="hidden"
						onchange={onFileChange}
					/>
					<Button size="sm" variant="outline" onclick={downloadReadings} disabled={downloading}>
						{downloading ? 'Формируем…' : 'Реестр показаний'}
					</Button>
					<Button size="sm" variant="outline" onclick={openPicker} disabled={uploading}>
						{uploading ? 'Обработка…' : 'Загрузить 1С'}
					</Button>
					<Button size="sm" onclick={downloadReport} disabled={reporting || selected.size === 0}>
						{reporting ? 'Формируем…' : 'Отчёт о выполнении'}
					</Button>
				</div>

				{#if reportError}
					<div class="text-sm text-destructive">{reportError}</div>
				{/if}

				{#if downloadError}
					<div class="text-sm text-destructive">{downloadError}</div>
				{/if}

				{#if uploadError}
					<div class="text-sm text-destructive">{uploadError}</div>
				{/if}

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
	</div>
{/if}
