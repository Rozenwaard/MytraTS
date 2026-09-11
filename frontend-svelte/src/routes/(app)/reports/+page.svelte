<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { queryClient } from '$lib/query';
	import {
		fetchFinReport,
		addToReport,
		uploadDiscrepancies,
		rollbackDiscrepancies,
		discardDiscrepancies,
		recheckTasks,
		startFinReportDownload,
		fetchFinReportDownloadProgress,
		fetchFinReportDownloadResult,
		type FinCardData,
		type FinReportData
	} from '$lib/api/fin-report';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { auth } from '$lib/store/auth.svelte';
	import { toast } from '$lib/store/toast.svelte';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';

	const MONTHS = [
		'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
		'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
	];

	const isAdmin = $derived(auth.user?.role === 'администратор');

	const options = (() => {
		const now = new Date();
		const opts: { value: string; label: string }[] = [];
		for (let i = 1; i <= 12; i++) {
			const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
			opts.push({
				value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
				label: MONTHS[d.getMonth()]
			});
		}
		return opts;
	})();

	let period = $state('');
	let reportOpen = $state(false);
	let expanded = $state<Set<string>>(new Set());

	const query = createQuery<FinReportData>(
		toStore(() => ({
			queryKey: ['fin-report', period],
			queryFn: () => fetchFinReport(period),
			enabled: isAdmin
		}))
	);
	const result = fromStore(query);
	const data = $derived(result.current.data);
	const loading = $derived(result.current.isPending);

	let adding = $state(false);
	let uploading = $state(false);
	let discrepanciesResult = $state<{ batchId: string; updated: number; notFound: number } | null>(null);
	let discrepanciesBusy = $state(false);
	let rechecking = $state(false);
	let downloading = $state(false);
	let downloadDone = $state(0);
	let downloadTotal = $state(0);

	let discrepanciesInput = $state<HTMLInputElement | undefined>(undefined);
	let recheckInput = $state<HTMLInputElement | undefined>(undefined);

	const fmtMoney = (v: number) =>
		v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽';

	function periodLabel(p: string): string {
		if (!p) return 'Ещё не в отчёте';
		const [year, month] = p.split('-');
		return `Отчёт за ${MONTHS[Number(month) - 1]} ${year}`;
	}

	function selectPeriod(p: string) {
		period = p;
		reportOpen = false;
	}

	function toggleExpand(key: string) {
		const next = new Set(expanded);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		expanded = next;
	}

	async function handleAdd() {
		adding = true;
		try {
			const res = await addToReport(period);
			toast(`Добавлено в отчёт ${res.period}: ${res.updated}`);
			await queryClient.invalidateQueries({ queryKey: ['fin-report', period] });
		} catch {
			toast('Ошибка добавления в отчёт');
		} finally {
			adding = false;
		}
	}

	function openDiscrepancies() {
		if (discrepanciesInput) {
			discrepanciesInput.value = '';
			discrepanciesInput.click();
		}
	}

	async function handleDiscrepanciesFile(file: File | undefined) {
		if (!file) return;
		if (!file.name.toLowerCase().endsWith('.txt')) {
			toast('Нужен файл .txt');
			return;
		}
		uploading = true;
		try {
			const res = await uploadDiscrepancies(file);
			discrepanciesResult = { batchId: res.batch_id, updated: res.updated, notFound: res.not_found };
			await queryClient.invalidateQueries({ queryKey: ['fin-report', period] });
		} catch {
			toast('Ошибка загрузки разногласий');
		} finally {
			uploading = false;
		}
	}

	async function confirmDiscrepancies() {
		if (!discrepanciesResult || discrepanciesBusy) return;
		discrepanciesBusy = true;
		try {
			await discardDiscrepancies(discrepanciesResult.batchId);
			toast('Изменения сохранены');
		} catch {
			toast('Ошибка фиксации изменений');
		} finally {
			discrepanciesBusy = false;
			discrepanciesResult = null;
			await queryClient.invalidateQueries({ queryKey: ['fin-report', period] });
		}
	}

	async function handleRollbackDiscrepancies() {
		if (!discrepanciesResult || discrepanciesBusy) return;
		discrepanciesBusy = true;
		try {
			const res = await rollbackDiscrepancies(discrepanciesResult.batchId);
			toast(`Откат выполнен: восстановлено ${res.restored}`);
		} catch {
			toast('Ошибка отката разногласий');
		} finally {
			discrepanciesBusy = false;
			discrepanciesResult = null;
			await queryClient.invalidateQueries({ queryKey: ['fin-report', period] });
		}
	}

	function openRecheck() {
		if (recheckInput) {
			recheckInput.value = '';
			recheckInput.click();
		}
	}

	async function handleRecheckFile(file: File | undefined) {
		if (!file) return;
		if (!file.name.toLowerCase().endsWith('.txt')) {
			toast('Нужен файл .txt');
			return;
		}
		rechecking = true;
		try {
			const res = await recheckTasks(file);
			const url = URL.createObjectURL(res.blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = 'Повторная_проверка.xlsx';
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
			toast(`Повторная проверка: обновлено ${res.updated} | не найдено ${res.not_found}`);
			await queryClient.invalidateQueries({ queryKey: ['fin-report', period] });
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка повторной проверки');
		} finally {
			rechecking = false;
		}
	}

	async function handleDownload() {
		if (downloading || !period) return;
		downloading = true;
		downloadDone = 0;
		downloadTotal = 6;
		try {
			const { download_id } = await startFinReportDownload(period);
			for (;;) {
				await new Promise((r) => setTimeout(r, 400));
				const p = await fetchFinReportDownloadProgress(download_id);
				if (p.status === 'error') {
					toast(p.message || 'Ошибка формирования отчёта');
					return;
				}
				downloadDone = p.done;
				downloadTotal = p.total;
				if (p.status === 'complete') break;
			}
			const blob = await fetchFinReportDownloadResult(download_id);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `Отчёт_${period}.zip`;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch {
			toast('Ошибка скачивания отчёта');
		} finally {
			downloading = false;
		}
	}

	const cards: { key: keyof FinReportData['cards']; label: string }[] = [
		{ key: 'completed', label: 'Заданий завершено' },
		{ key: 'without_reestr', label: 'Исполнено без реестров' },
		{ key: 'with_errors', label: 'Заданий с ошибками' },
		{ key: 'ready', label: 'Готово к отчёту' }
	];
</script>

{#if auth.loading}
	<div class="p-6"><Skeleton class="h-6 w-40" /></div>
{:else if !isAdmin}
	<div class="p-6 text-sm text-muted-foreground">Нет доступа</div>
{:else}
	<div class="flex h-full flex-col gap-3 overflow-auto p-3">
		<div class="flex flex-wrap items-center gap-2">
			<select
				value={period}
				onchange={(e) => selectPeriod((e.currentTarget as HTMLSelectElement).value)}
				class="h-8 rounded-md border border-input bg-background px-2 text-sm"
			>
				<option value="">Выберите период</option>
				{#each options as o (o.value)}
					<option value={o.value}>{o.label}</option>
				{/each}
			</select>

			<Button size="sm" onclick={handleAdd} disabled={adding || (period !== '' && !reportOpen)}>
				{adding ? 'Добавляем…' : 'Добавить в отчёт'}
			</Button>

			{#if period}
				<label
					class="flex cursor-pointer items-center gap-2 select-none"
					title="Разблокировать кнопку «Добавить в отчёт»"
				>
					<input type="checkbox" bind:checked={reportOpen} class="size-4" />
					<span class="text-sm">Разблокировать</span>
				</label>

				<Button size="sm" class="bg-destructive text-destructive-foreground hover:bg-destructive/80" onclick={openDiscrepancies} disabled={uploading}>
					{uploading ? 'Обрабатываем…' : 'Разногласия'}
				</Button>

				<Button variant="outline" size="sm" onclick={openRecheck} disabled={rechecking}>
					{rechecking ? 'Проверяем…' : 'Повторная проверка'}
				</Button>

				<Button variant="outline" size="sm" onclick={handleDownload} disabled={downloading}>
					{downloading ? `Формируем… ${downloadDone}/${downloadTotal}` : 'Скачать отчёт'}
				</Button>
			{/if}

			<input
				bind:this={discrepanciesInput}
				type="file"
				accept=".txt"
				class="hidden"
				onchange={(e) => handleDiscrepanciesFile(e.currentTarget.files?.[0])}
			/>
			<input
				bind:this={recheckInput}
				type="file"
				accept=".txt"
				class="hidden"
				onchange={(e) => handleRecheckFile(e.currentTarget.files?.[0])}
			/>
		</div>

		<div class="flex gap-6">
			<div class="min-w-0 flex-1">
				{#if loading || !data}
					<div class="flex flex-wrap gap-3">
						{#each Array(4) as _}
							<Skeleton class="h-28 w-44" />
						{/each}
					</div>
				{:else}
					<div class="flex flex-wrap items-start gap-3">
						{#each cards as c (c.key)}
							{@render FinCard(c, data.cards[c.key])}
						{/each}
					</div>
				{/if}
			</div>

			<div class="w-[330px] shrink-0 self-start rounded-md border bg-card p-4">
				<div class="mb-2 text-xs font-medium text-muted-foreground">{periodLabel(period)}</div>
				{#if loading || !data}
					<Skeleton class="h-4 w-full" />
				{:else if data.work_types.length === 0}
					<div class="text-sm text-muted-foreground">
						{period ? 'Нет данных за период' : 'Все работы включены в отчёт'}
					</div>
				{:else}
					<div class="space-y-1">
						{#each data.work_types as w (w.label)}
							<div class="flex justify-between gap-2 text-sm">
								<span class="text-muted-foreground">{w.label}</span>
								<span class="font-semibold tabular-nums">{w.count.toLocaleString('ru-RU')}</span>
							</div>
						{/each}
					</div>
				{/if}
				<div class="mt-3 space-y-1 border-t pt-2 text-sm">
					<div class="flex justify-between font-semibold">
						<span>Итого</span>
						<span class="tabular-nums">{data ? fmtMoney(data.total_cost) : fmtMoney(0)}</span>
					</div>
					<div class="flex justify-between text-muted-foreground">
						<span>ПСК</span>
						<span class="tabular-nums">{data ? fmtMoney(data.cost_psk) : fmtMoney(0)}</span>
					</div>
					<div class="flex justify-between text-muted-foreground">
						<span>РЛЭ</span>
						<span class="tabular-nums">{data ? fmtMoney(data.cost_rle) : fmtMoney(0)}</span>
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}

<svelte:window onkeydown={(e) => { if (discrepanciesResult && e.key === 'Escape') confirmDiscrepancies(); }} />

{#if discrepanciesResult}
	<button
		type="button"
		class="fixed inset-0 z-40 bg-black/50"
		aria-label="Закрыть"
		onclick={confirmDiscrepancies}
	></button>

	<div class="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-4">
		<div
			class="pointer-events-auto w-full max-w-md rounded-lg border bg-card p-6 shadow-lg"
			role="dialog"
			aria-modal="true"
			tabindex="-1"
		>
			<h2 class="text-lg font-semibold">Разногласия</h2>
			<p class="mt-2 text-sm text-muted-foreground">
				Изменения применены: удалено исполнение для {discrepanciesResult.updated} строк.
			</p>
			<div class="mt-6 flex justify-end gap-4">
				<Button variant="outline" size="sm" onclick={handleRollbackDiscrepancies} disabled={discrepanciesBusy}>
					Откатить
				</Button>
				<Button size="sm" onclick={confirmDiscrepancies} disabled={discrepanciesBusy}>
					Сохранить
				</Button>
			</div>
		</div>
	</div>
{/if}

{#snippet FinCard(def: { key: string; label: string }, card: FinCardData)}
	<div class="min-w-[170px] rounded-md border bg-card">
		<button class="w-full p-4 text-left" onclick={() => toggleExpand(def.key)}>
			<div class="text-xs text-muted-foreground">{def.label}</div>
			<div class="flex items-center gap-1 text-2xl font-semibold tabular-nums">
				{card.total.toLocaleString('ru-RU')}
				<ChevronDown
					class={`size-4 text-muted-foreground transition-transform ${expanded.has(def.key) ? 'rotate-180' : ''}`}
				/>
			</div>
			<div class="mt-1 text-sm text-muted-foreground tabular-nums">{fmtMoney(card.cost)}</div>
		</button>
		{#if expanded.has(def.key)}
			<div class="space-y-1 px-4 pb-3">
				{#if card.by_locale.length === 0}
					<div class="text-xs text-muted-foreground">Нет данных</div>
				{:else}
					{#each card.by_locale as b (b.locale)}
						<div class="flex justify-between gap-4 text-sm">
							<span class="text-muted-foreground">{b.locale}</span>
							<span class="font-semibold tabular-nums">{b.count.toLocaleString('ru-RU')}</span>
						</div>
					{/each}
				{/if}
			</div>
		{/if}
	</div>
{/snippet}
