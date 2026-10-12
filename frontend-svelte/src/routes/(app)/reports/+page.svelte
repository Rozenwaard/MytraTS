<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { tick } from 'svelte';
	import { fly } from 'svelte/transition';
	import { queryClient } from '$lib/query';
	import {
		fetchFinReport,
		fetchFinReportPeriods,
		fetchFinReportDepts,
		supplementReport,
		fetchSupplementSum,
		startArchive,
		fetchArchiveProgress,
		addToReport,
		uploadDiscrepancies,
		rollbackDiscrepancies,
		discardDiscrepancies,
		recheckTasks,
		startFinReportDownload,
		fetchFinReportDownloadProgress,
		fetchFinReportDownloadResult,
		type FinCardData,
		type FinReportData,
		type ArchiveProgress,
		type FinReportDepts,
		type FinReportPeriod,
		type FinReportPeriods
	} from '$lib/api/fin-report';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { auth } from '$lib/store/auth.svelte';
	import { toast } from '$lib/store/toast.svelte';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';

	const MONTHS = [
		'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
		'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
	];

	const isAdmin = $derived(auth.user?.role === 'администратор');

	const periodsQuery = createQuery<FinReportPeriods>(
		toStore(() => ({
			queryKey: ['fin-report-periods'],
			queryFn: () => fetchFinReportPeriods(),
			enabled: isAdmin
		}))
	);
	const periodsResult = fromStore(periodsQuery);

	let period = $state('');
	let periods = $state<FinReportPeriod[]>([]);

	$effect(() => {
		const d = periodsResult.current.data;
		if (!d) return;
		periods = d.periods;
		if (!period) {
			const first = d.periods[0]?.value ?? '';
			period = d.periods.some((p) => p.value === d.default) ? d.default : first;
		}
	});

	function tileClass(p: FinReportPeriod): string {
		const base = 'w-full rounded-md border px-3 py-2 text-left transition-colors';
		const empty = (!p.has_rows && !p.is_current) || p.is_archived || !p.can_form;
		if (period === p.value) {
			return `${base} border-primary bg-primary/10`;
		}
		if (empty) {
			return `${base} border-dashed border-muted-foreground/50 bg-muted/50 text-muted-foreground opacity-60 hover:bg-muted`;
		}
		return `${base} border-input bg-background hover:bg-muted`;
	}
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

	const selectedCategory = $derived(periods.find((p) => p.value === period)?.category ?? '');
	const isOld = $derived(selectedCategory === 'old');
	const isPrevious = $derived(selectedCategory === 'previous');
	const isCurrent = $derived(selectedCategory === 'current');
	const isArchived = $derived(periods.find((p) => p.value === period)?.is_archived ?? false);
	const canForm = $derived(periods.find((p) => p.value === period)?.can_form ?? false);

	const deptsQuery = createQuery<FinReportDepts>(
		toStore(() => ({
			queryKey: ['fin-report-depts', period],
			queryFn: () => fetchFinReportDepts(period),
			enabled: isAdmin && (isOld || isPrevious || isCurrent) && !!period
		}))
	);
	const deptsResult = fromStore(deptsQuery);
	const depts = $derived(deptsResult.current.data);
	const deptsLoading = $derived(deptsResult.current.isPending);

	const supplementSumQuery = createQuery<{ psk: number; rle: number }>(
		toStore(() => ({
			queryKey: ['fin-report-supplement-sum', period],
			queryFn: () => fetchSupplementSum(period),
			enabled: isAdmin && isPrevious && !!period
		}))
	);
	const supplementSumResult = fromStore(supplementSumQuery);
	const supplementSum = $derived(supplementSumResult.current.data ?? { psk: 0, rle: 0 });

	let archiving = $state(false);
	let archiveProgress = $state<ArchiveProgress | null>(null);

	function archiveStage(p: ArchiveProgress | null): { label: string; percent: number } {
		switch (p?.status) {
			case 'starting': return { label: 'Старт…', percent: 5 };
			case 'moving': return { label: 'Перенос строк…', percent: 40 };
			case 'consumers': return { label: 'Потребители…', percent: 80 };
			case 'complete': return { label: 'Готово', percent: 100 };
			case 'error': return { label: 'Ошибка', percent: 100 };
			default: return { label: '', percent: 0 };
		}
	}

	let forming = $state(false);
	let carouselEl = $state<HTMLDivElement | undefined>(undefined);
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
	}

	function toggleExpand(key: string) {
		const next = new Set(expanded);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		expanded = next;
	}

	async function handleForm() {
		if (forming || !period) return;
		forming = true;
		try {
			const res = await addToReport(period);
			toast(`Сформирован отчёт ${res.period}: ${res.updated}`);
			await queryClient.invalidateQueries({ queryKey: ['fin-report'] });
			await queryClient.invalidateQueries({ queryKey: ['fin-report-depts'] });
			await queryClient.invalidateQueries({ queryKey: ['fin-report-periods'] });
			await queryClient.refetchQueries({ queryKey: ['fin-report-periods'] });
			await tick();
			carouselEl?.scrollTo({ top: 0, behavior: 'smooth' });
		} catch {
			toast('Ошибка формирования отчёта');
		} finally {
			forming = false;
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

	async function handleArchive() {
		if (archiving || !period) return;
		archiving = true;
		archiveProgress = { status: 'starting', moved: 0, consumers: 0 };
		try {
			const { archive_id } = await startArchive(period);
			const timer = setInterval(async () => {
				try {
					const p = await fetchArchiveProgress(archive_id);
					archiveProgress = p;
					if (p.status === 'complete' || p.status === 'error') {
						clearInterval(timer);
						if (p.status === 'complete') {
							// прячем прогресс и кнопку одновременно
							archiving = false;
							periods = periods.map((pp) => (pp.value === period ? { ...pp, is_archived: true } : pp));
							toast(`Отправлено в архив: ${p.moved}`);
							await queryClient.invalidateQueries({ queryKey: ['fin-report'] });
							await queryClient.invalidateQueries({ queryKey: ['fin-report-periods'] });
							await queryClient.invalidateQueries({ queryKey: ['fin-report-depts'] });
						} else {
							archiving = false;
							toast('Ошибка отправки в архив');
						}
					}
				} catch {
					clearInterval(timer);
					archiving = false;
					archiveProgress = { status: 'error', moved: 0, consumers: 0 };
				}
			}, 500);
		} catch {
			archiving = false;
			archiveProgress = { status: 'error', moved: 0, consumers: 0 };
		}
	}

	let supplementing = $state(false);
	let confirmSupplement = $state(false);
	let supplementCustomer = $state('');
	let supplementAmount = $state(0);

	function handleSupplement(customer: string) {
		if (!period) return;
		supplementCustomer = customer;
		supplementAmount = customer === 'ПСК' ? (supplementSum?.psk ?? 0) : (supplementSum?.rle ?? 0);
		confirmSupplement = true;
	}

	async function confirmSupplementAction() {
		confirmSupplement = false;
		supplementing = true;
		try {
			const res = await supplementReport(period, supplementCustomer);
			toast(`Дополнено: ${res.updated}`);
			await queryClient.invalidateQueries({ queryKey: ['fin-report'] });
			await queryClient.invalidateQueries({ queryKey: ['fin-report-depts'] });
			await queryClient.invalidateQueries({ queryKey: ['fin-report-supplement-sum'] });
		} catch {
			toast('Ошибка дополнения отчёта');
		} finally {
			supplementing = false;
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
	<div class="flex h-full overflow-hidden">
		<div bind:this={carouselEl} class="w-44 shrink-0 space-y-2 overflow-auto border-r p-3">
			{#each periods as p (p.value)}
				<button
					type="button"
					class={tileClass(p)}
					onclick={() => selectPeriod(p.value)}
					in:fly={{ y: -8, duration: 180 }}
				>
					<div class="text-base font-semibold">{MONTHS[Number(p.value.split('-')[1]) - 1]}</div>
					<div class="text-xs text-muted-foreground">
						{p.value.split('-')[0]}{p.is_archived ? ' · архив' : ''}{!p.can_form ? ' · скоро' : ''}
					</div>
				</button>
			{/each}
		</div>

		<div class="flex min-w-0 flex-1 flex-col gap-3 overflow-auto p-3">
			{#if isOld}
				<div class="flex flex-wrap items-center gap-2">
					<Button variant="outline" size="sm" onclick={handleDownload} disabled={downloading}>
						{downloading ? `Формируем… ${downloadDone}/${downloadTotal}` : 'Скачать отчёт'}
					</Button>
					{#if !isArchived}
						<Button size="sm" class="bg-destructive text-destructive-foreground hover:bg-destructive/80" onclick={handleArchive} disabled={archiving}>
							{archiving ? 'Отправляем…' : 'Отправить в архив'}
						</Button>
						{#if archiving && archiveProgress}
							<div class="w-44">
								<div class="mb-1 text-xs text-muted-foreground">{archiveStage(archiveProgress).label}</div>
								<div class="h-2 w-full overflow-hidden rounded-full bg-muted">
									<div class="h-full bg-primary transition-all" style={`width: ${archiveStage(archiveProgress).percent}%`}></div>
								</div>
							</div>
						{/if}
					{/if}
				</div>
			{:else if isPrevious}
				<div class="flex flex-wrap items-center gap-2">
					<Button size="sm" onclick={() => handleSupplement('ПСК')} disabled={supplementing}>
						{supplementing ? 'Дополняем…' : `Дополнить ПСК · ${fmtMoney(supplementSum.psk)}`}
					</Button>
					<Button size="sm" onclick={() => handleSupplement('РЛЭ')} disabled={supplementing}>
						{supplementing ? 'Дополняем…' : `Дополнить РЛЭ · ${fmtMoney(supplementSum.rle)}`}
					</Button>

					<Button size="sm" class="bg-destructive text-destructive-foreground hover:bg-destructive/80" onclick={openDiscrepancies} disabled={uploading}>
						{uploading ? 'Обрабатываем…' : 'Разногласия'}
					</Button>

					<Button variant="outline" size="sm" onclick={openRecheck} disabled={rechecking}>
						{rechecking ? 'Проверяем…' : 'Повторная проверка'}
					</Button>

					<Button variant="outline" size="sm" onclick={handleDownload} disabled={downloading}>
						{downloading ? `Формируем… ${downloadDone}/${downloadTotal}` : 'Скачать отчёт'}
					</Button>

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
			{:else}
				<div class="flex flex-wrap items-center gap-2">
					<Button size="sm" onclick={handleForm} disabled={forming || !canForm}>
						{forming ? 'Формируем…' : 'Сформировать отчёт'}
					</Button>
					{#if !canForm}
						<span class="text-xs text-muted-foreground">Период ещё не наступил</span>
					{/if}
				</div>
			{/if}

			<div class="flex gap-6">
				<div class="min-w-0 flex-1">
					{#if isOld || isPrevious || isCurrent}
						<div class="rounded-md border bg-card">
							<Table containerClass="overflow-auto">
								<TableHeader>
									<TableRow class="hover:bg-transparent">
										<TableHead class="whitespace-nowrap">Отделение</TableHead>
										{#if isCurrent}
											<TableHead class="whitespace-nowrap text-right">Выполненные работы</TableHead>
											<TableHead class="whitespace-nowrap text-right">Недопуски в штуках</TableHead>
											<TableHead class="whitespace-nowrap text-right">Не закрыто реестрами</TableHead>
										{:else}
											<TableHead class="whitespace-nowrap text-right">Всего работ</TableHead>
											<TableHead class="whitespace-nowrap text-right">Результативных</TableHead>
											<TableHead class="whitespace-nowrap text-right">Нерезультативных</TableHead>
										{/if}
										<TableHead class="whitespace-nowrap text-right">Сумма</TableHead>
									</TableRow>
								</TableHeader>
								<TableBody>
									{#if deptsLoading || !depts}
										{#each Array(5) as _}
											<TableRow>
												<TableCell><Skeleton class="h-4 w-40" /></TableCell>
												{#if isCurrent}
													<TableCell><Skeleton class="h-4 w-16" /></TableCell>
													<TableCell><Skeleton class="h-4 w-16" /></TableCell>
													<TableCell><Skeleton class="h-4 w-16" /></TableCell>
													<TableCell><Skeleton class="h-4 w-20" /></TableCell>
												{:else}
													<TableCell><Skeleton class="h-4 w-16" /></TableCell>
													<TableCell><Skeleton class="h-4 w-16" /></TableCell>
													<TableCell><Skeleton class="h-4 w-16" /></TableCell>
													<TableCell><Skeleton class="h-4 w-20" /></TableCell>
												{/if}
											</TableRow>
										{/each}
									{:else}
										{#each depts.rows as r (r.org)}
											<TableRow>
												<TableCell class="whitespace-nowrap">{r.org}</TableCell>
												{#if isCurrent}
													<TableCell class="whitespace-nowrap text-right tabular-nums">{r.done.toLocaleString('ru-RU')}</TableCell>
													<TableCell class="whitespace-nowrap text-right tabular-nums">{r.nedopusk.toLocaleString('ru-RU')}</TableCell>
													<TableCell class="whitespace-nowrap text-right tabular-nums">{r.not_closed.toLocaleString('ru-RU')}</TableCell>
												{:else}
													<TableCell class="whitespace-nowrap text-right tabular-nums">{r.total.toLocaleString('ru-RU')}</TableCell>
													<TableCell class="whitespace-nowrap text-right tabular-nums">{r.successful.toLocaleString('ru-RU')}</TableCell>
													<TableCell class="whitespace-nowrap text-right tabular-nums">{r.unsuccessful.toLocaleString('ru-RU')}</TableCell>
												{/if}
												<TableCell class="whitespace-nowrap text-right tabular-nums">{fmtMoney(r.sum)}</TableCell>
											</TableRow>
										{/each}
										<TableRow class="font-semibold">
											<TableCell>{depts.total.org}</TableCell>
											{#if isCurrent}
												<TableCell class="text-right tabular-nums">{depts.total.done.toLocaleString('ru-RU')}</TableCell>
												<TableCell class="text-right tabular-nums">{depts.total.nedopusk.toLocaleString('ru-RU')}</TableCell>
												<TableCell class="text-right tabular-nums">{depts.total.not_closed.toLocaleString('ru-RU')}</TableCell>
											{:else}
												<TableCell class="text-right tabular-nums">{depts.total.total.toLocaleString('ru-RU')}</TableCell>
												<TableCell class="text-right tabular-nums">{depts.total.successful.toLocaleString('ru-RU')}</TableCell>
												<TableCell class="text-right tabular-nums">{depts.total.unsuccessful.toLocaleString('ru-RU')}</TableCell>
											{/if}
											<TableCell class="text-right tabular-nums">{fmtMoney(depts.total.sum)}</TableCell>
										</TableRow>
									{/if}
								</TableBody>
							</Table>
						</div>
					{:else}
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

{#if confirmSupplement}
	<button
		type="button"
		class="fixed inset-0 z-40 bg-black/50"
		aria-label="Закрыть"
		onclick={() => (confirmSupplement = false)}
	></button>

	<div class="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-4">
		<div
			class="pointer-events-auto w-full max-w-md rounded-lg border bg-card p-6 shadow-lg"
			role="dialog"
			aria-modal="true"
			tabindex="-1"
		>
			<h2 class="text-lg font-semibold">Дополнить {supplementCustomer}</h2>
			<p class="mt-2 text-sm text-muted-foreground">
				Дополнить {periodLabel(period)} ({supplementCustomer})? Сумма вырастет на {fmtMoney(supplementAmount)}.
			</p>
			<div class="mt-6 flex justify-end gap-4">
				<Button variant="outline" size="sm" onclick={() => (confirmSupplement = false)} disabled={supplementing}>
					Отмена
				</Button>
				<Button size="sm" onclick={confirmSupplementAction} disabled={supplementing}>
					{supplementing ? 'Дополняем…' : 'Дополнить'}
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
