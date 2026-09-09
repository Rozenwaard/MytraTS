<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import {
		createTable,
		getCoreRowModel,
		getSortedRowModel,
		type ColumnDef,
		type SortingState
	} from '@tanstack/table-core';
	import { api } from '$lib/api/client';
	import {
		buildMainAflQuery,
		createReestr,
		downloadReestrUrl,
		fetchAllTaskNumbers,
		fetchMainAflStats,
		type MainAflRow,
		type MainAflResponse,
		type MainAflStats
	} from '$lib/api/main-afl';
	import { VISIBLE_COLUMNS, EXPAND_GROUPS } from '$lib/columns';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import ListChecks from '@lucide/svelte/icons/list-checks';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import Coins from '@lucide/svelte/icons/coins';
	import type { Component } from 'svelte';
	import { search } from '$lib/store/search.svelte';
	import ChevronsLeft from '@lucide/svelte/icons/chevrons-left';
	import ChevronsRight from '@lucide/svelte/icons/chevrons-right';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Printer from '@lucide/svelte/icons/printer';
	import { queryClient } from '$lib/query';
	import { toast } from '$lib/store/toast.svelte';
	import { auth } from '$lib/store/auth.svelte';
	import { Input } from '$lib/components/ui/input';
	import Search from '@lucide/svelte/icons/search';
	import { copyText } from '$lib/clipboard';

	const HEADER_ICONS: Partial<Record<keyof MainAflRow, Component>> = {
		reestr_number: ListChecks,
		errors: TriangleAlert,
		norm: Coins
	};

	const columns: ColumnDef<MainAflRow>[] = VISIBLE_COLUMNS.map((c) => ({
		accessorKey: c.key,
		header: c.header
	}));

	const perPage = 50;
	let page = $state(1);
	let sorting = $state<SortingState>([]);
	let expanded = $state<Set<string>>(new Set());

	let searchValue = $state('');
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		const value = search.value;
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			searchValue = value;
		}, 300);
	});

	let reportOptions = $state<string[]>([]);
	let reportChoice = $state<Record<string, string>>({});

	const canChangeReport = $derived(auth.user?.role === 'администратор');

	const canSelectForReestr = $derived(
		auth.user?.role === 'менеджер' || auth.user?.role === 'оператор' || auth.user?.role === 'работник'
	);

	let selected = $state<Set<string>>(new Set());
	let allSelected = $state(false);
	let selectingAll = $state(false);
	let done_day = $state('');
	let stats = $state<MainAflStats | null>(null);

	let customer = $state<string | undefined>(undefined);
	let taskType = $state<string | undefined>(undefined);
	let onlyCompleted = $state(false);
	let taskReport = $state<string | undefined>(undefined);
	let executorFilter = $state<string | undefined>(undefined);
	let executorOrg = $state<string | undefined>(undefined);
	let onlyWithoutReestr = $state(false);

	function toggleSelected(id: string) {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
		allSelected = false;
	}

	async function copyTask(id: string) {
		if (id) await copyText(id);
	}

	$effect(() => {
		fetchMainAflStats()
			.then((s) => (stats = s))
			.catch(() => {});
	});

	const doneDays = $derived(stats?.done_days ?? []);
	const showDepartments = $derived(
		auth.user?.role === 'администратор' || auth.user?.role === 'специалист'
	);
	const filteredTaskReports = $derived(
		(stats?.task_reports ?? []).filter(
			(t) => !['Не выполнено', 'Дубли', 'Ручная проверка'].includes(t.label)
		)
	);

	function splitTwoColumns<T>(items: T[]): [T[], T[]] {
		return [items.slice(0, 7), items.slice(7, 14)];
	}

	const reportCols = $derived(splitTwoColumns(filteredTaskReports));
	const deptCols = $derived(splitTwoColumns(stats?.depts ?? []));

	function deptLabel(d: string) {
		return d.replace(/ отделение$/, '');
	}

	function resetFilters() {
		search.value = '';
		customer = undefined;
		taskType = undefined;
		onlyCompleted = false;
		taskReport = undefined;
		executorFilter = undefined;
		executorOrg = undefined;
		onlyWithoutReestr = false;
		done_day = '';
		page = 1;
	}

	function toggleStat(label: string) {
		if (label === 'ПСК') customer = customer === 'ПСК' ? undefined : 'ПСК';
		else if (label === 'РЛЭ') customer = customer === 'РЛЭ' ? undefined : 'РЛЭ';
		else if (label === 'План') taskType = taskType === 'Плановый' ? undefined : 'Плановый';
		else if (label === 'Внеплан') taskType = taskType === 'Внеплановый' ? undefined : 'Внеплановый';
		else if (label === 'Выполнено') onlyCompleted = !onlyCompleted;
		else if (label === 'Не выполнено') onlyCompleted = false;
		page = 1;
	}

	function toggleTaskReport(label: string) {
		taskReport = taskReport === label ? undefined : label;
		page = 1;
	}

	function toggleExecutor(label: string) {
		executorFilter = executorFilter === label ? undefined : label;
		page = 1;
	}

	function toggleDept(label: string) {
		executorOrg = executorOrg === label ? undefined : label;
		page = 1;
	}

	async function handleCreateReestr() {
		if (selected.size === 0) {
			toast('Не выбраны строки');
			return;
		}
		try {
			const result = await createReestr([...selected]);
			const parts = result.reestrs.map((r) =>
				r.reestr_number === 'Отклонён'
					? `${r.task_report}: отклонён`
					: `${r.reestr_number} — ${r.task_report} (${r.count})`
			);
			const blockedMsg = result.blocked?.length ? ` | Стоп-фактор: ${result.blocked.length}` : '';
			toast((parts.join(' | ') || 'Готово') + blockedMsg);
			selected = new Set();
			allSelected = false;
			queryClient.invalidateQueries({ queryKey: ['main-afl'] });
		} catch {
			toast('Ошибка создания реестра');
		}
	}

	$effect(() => {
		api<string[]>('/api/task-reports')
			.then((list) => (reportOptions = list))
			.catch(() => {});
	});

	const sortKey = $derived(sorting[0]?.id ?? '');
	const sortOrder = $derived(sorting[0]?.desc ? 'desc' : 'asc');

	const query = createQuery<MainAflResponse>(
		toStore(() => ({
			queryKey: [
				'main-afl',
				page,
				sortKey,
				sortOrder,
				searchValue,
				done_day,
				customer,
				taskType,
				onlyCompleted,
				taskReport,
				executorFilter,
				executorOrg,
				onlyWithoutReestr
			],
			queryFn: () =>
				api<MainAflResponse>(
					`/api/main-afl?${buildMainAflQuery({
						page,
						per_page: perPage,
						sort: sortKey || undefined,
						order: sortKey ? sortOrder : undefined,
						search: searchValue || undefined,
						done_day: done_day || undefined,
						customer,
						task_type: taskType,
						only_completed: onlyCompleted || undefined,
						task_report: taskReport,
						executor_filter: executorFilter,
						executor_org: executorOrg,
						only_without_reestr: onlyWithoutReestr || undefined
					})}`
				)
		}))
	);

	const result = fromStore(query);
	const rows = $derived(result.current.data?.rows ?? []);
	const isPending = $derived(result.current.isPending);

	function currentFilterParams() {
		return {
			search: searchValue || undefined,
			done_day: done_day || undefined,
			customer,
			task_type: taskType,
			only_completed: onlyCompleted || undefined,
			task_report: taskReport,
			executor_filter: executorFilter,
			executor_org: executorOrg,
			only_without_reestr: onlyWithoutReestr || undefined
		};
	}

	async function toggleAllVisible() {
		if (selectingAll) return;
		selectingAll = true;
		try {
			const ids = await fetchAllTaskNumbers(currentFilterParams());
			if (allSelected) {
				selected = new Set();
				allSelected = false;
			} else {
				selected = new Set(ids);
				allSelected = ids.length > 0;
				toast(ids.length ? `Выбрано: ${ids.length}` : 'Нет строк в текущей фильтрации');
			}
		} catch {
			toast('Ошибка выбора строк');
		} finally {
			selectingAll = false;
		}
	}

	$effect(() => {
		// сброс «выбрано всё» при смене фильтров
		searchValue;
		customer;
		taskType;
		onlyCompleted;
		taskReport;
		executorFilter;
		executorOrg;
		onlyWithoutReestr;
		done_day;
		allSelected = false;
	});

	const table = $derived(
		createTable({
			data: rows,
			columns,
			onStateChange: () => {},
			renderFallbackValue: null,
			getCoreRowModel: getCoreRowModel(),
			getSortedRowModel: getSortedRowModel(),
			manualSorting: true,
			manualPagination: true,
			state: { sorting }
		})
	);

	const total = $derived(result.current.data?.total ?? 0);
	const totalPages = $derived(Math.max(1, Math.ceil(total / perPage)));

	function setSort(key: string) {
		const current = sorting[0];
		if (current?.id === key) {
			if (current.desc) sorting = [];
			else sorting = [{ id: key, desc: true }];
		} else {
			sorting = [{ id: key, desc: false }];
		}
	}

	function sortIndicator(key: string) {
		const current = sorting[0];
		if (current?.id !== key) return '';
		return current.desc ? ' ↓' : ' ↑';
	}

	function toggleExpanded(id: string) {
		const next = new Set(expanded);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		expanded = next;
	}

	function goToPage(p: number) {
		if (p >= 1 && p <= totalPages) page = p;
	}

	function pageItems(current: number, total: number): (number | '…')[] {
		if (total <= 1) return [1];
		const neighbors = new Set<number>([1, total]);
		for (let i = current - 2; i <= current + 2; i++) {
			if (i >= 1 && i <= total) neighbors.add(i);
		}
		const sorted = [...neighbors].sort((a, b) => a - b);
		const result: (number | '…')[] = [];
		let prev = 0;
		for (const n of sorted) {
			if (n - prev > 1) result.push('…');
			result.push(n);
			prev = n;
		}
		return result;
	}

	async function resetReestr(row: MainAflRow) {
		const tn = row.task_number;
		if (!tn) return;
		try {
			await api<{ cleared: number }>('/api/reestr/reset', {
				method: 'POST',
				body: JSON.stringify({ task_numbers: [tn] })
			});
			toast('Удалено из реестра');
			queryClient.invalidateQueries({ queryKey: ['main-afl'] });
		} catch {
			toast('Ошибка');
		}
	}

	async function changeReport(row: MainAflRow) {
		const tn = row.task_number;
		if (!tn) return;
		const chosen = reportChoice[tn];
		if (!chosen) return;
		try {
			await api('/api/main-afl/task-report', {
				method: 'PATCH',
				body: JSON.stringify({ task_numbers: [tn], task_report: chosen === '__none__' ? '' : chosen })
			});
			toast('Вид работ изменён');
			queryClient.invalidateQueries({ queryKey: ['main-afl'] });
		} catch {
			toast('Ошибка');
		}
	}
</script>

<div class="flex h-full flex-col gap-3 p-3">
	<div class="shrink-0 space-y-3">
		<div class="rounded-md border bg-card p-3">
			<div class="flex flex-wrap items-center gap-3">
				<div class="relative w-full max-w-sm">
					<Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
					<Input bind:value={search.value} placeholder="Поиск по адресу, № задания или л/с" class="bg-background pl-8" />
				</div>
				<select
					class={done_day
						? 'h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring'
						: 'h-9 rounded-md border border-input bg-background px-2 text-sm text-muted-foreground outline-none focus-visible:border-ring'}
					bind:value={done_day}
				>
					<option value="">Выберите дату работ</option>
					{#each doneDays as d (d)}
						<option value={d}>{d}</option>
					{/each}
				</select>
				<label class="flex cursor-pointer items-center gap-2 text-sm">
					<button
						type="button"
						role="switch"
						aria-checked={onlyWithoutReestr}
						aria-label={onlyWithoutReestr ? 'Без реестра' : 'Все строки'}
						class={onlyWithoutReestr
							? 'relative h-5 w-9 shrink-0 rounded-full bg-primary transition-colors'
							: 'relative h-5 w-9 shrink-0 rounded-full bg-border transition-colors'}
						onclick={() => (onlyWithoutReestr = !onlyWithoutReestr)}
					>
						<span class={`absolute left-0.5 top-0.5 size-4 rounded-full bg-white shadow-sm transition-transform ${onlyWithoutReestr ? 'translate-x-4' : ''}`}></span>
					</button>
					<span class="w-24 shrink-0">{onlyWithoutReestr ? 'Без реестра' : 'Все строки'}</span>
				</label>
				{#if canSelectForReestr}
					<Button size="sm" onclick={handleCreateReestr} disabled={selected.size === 0}>
						В реестр
					</Button>
				{/if}
				<Button variant="outline" size="sm" onclick={resetFilters}>Сброс фильтров</Button>
			</div>
		</div>
		<div class="rounded-md border bg-card p-3">
			<div class={showDepartments ? 'grid grid-cols-1 gap-6 text-sm sm:grid-cols-5' : 'grid grid-cols-1 gap-6 text-sm sm:grid-cols-3'}>
				<div>
					<div class="mb-1.5 text-xs font-medium text-muted-foreground">Статистика</div>
					<div class="flex flex-col gap-y-0.5 text-xs">
						{#each [
							{ label: 'ПСК', count: stats?.customers?.['ПСК'] },
							{ label: 'РЛЭ', count: stats?.customers?.['РЛЭ'] },
							{ label: 'План', count: stats?.plan },
							{ label: 'Внеплан', count: stats?.unplan },
							{ label: 'Выполнено', count: stats?.completed },
							{ label: 'Не выполнено', count: stats?.uncompleted }
						] as s (s.label)}
							<button class="flex cursor-pointer gap-1 text-left hover:underline" onclick={() => toggleStat(s.label)}>
								<span class="text-muted-foreground">{s.label}</span>
								<span class="ml-auto font-semibold tabular-nums">{s.count != null ? s.count.toLocaleString('ru-RU') : '—'}</span>
							</button>
						{/each}
					</div>
				</div>
				{#if showDepartments}
					<div class="sm:col-span-2">
						<div class="mb-1.5 text-xs font-medium text-muted-foreground">Вид работ</div>
						<div class="flex gap-4">
							<div class="flex flex-1 flex-col gap-y-0.5 text-xs">
								{#each reportCols[0] as tr (tr.label)}
									<button class="flex cursor-pointer gap-1 text-left hover:underline" onclick={() => toggleTaskReport(tr.label)}>
										<span class="text-muted-foreground">{tr.label}</span>
										<span class="ml-auto font-semibold tabular-nums">{tr.count.toLocaleString('ru-RU')}</span>
									</button>
								{/each}
							</div>
							<div class="flex flex-1 flex-col gap-y-0.5 text-xs">
								{#each reportCols[1] as tr (tr.label)}
									<button class="flex cursor-pointer gap-1 text-left hover:underline" onclick={() => toggleTaskReport(tr.label)}>
										<span class="text-muted-foreground">{tr.label}</span>
										<span class="ml-auto font-semibold tabular-nums">{tr.count.toLocaleString('ru-RU')}</span>
									</button>
								{/each}
							</div>
						</div>
					</div>
				{:else}
					<div>
						<div class="mb-1.5 text-xs font-medium text-muted-foreground">Вид работ</div>
						<div class="flex flex-col gap-y-0.5 text-xs">
							{#each filteredTaskReports as tr (tr.label)}
								<button class="flex cursor-pointer gap-1 text-left hover:underline" onclick={() => toggleTaskReport(tr.label)}>
									<span class="text-muted-foreground">{tr.label}</span>
									<span class="ml-auto font-semibold tabular-nums">{tr.count.toLocaleString('ru-RU')}</span>
								</button>
							{/each}
						</div>
					</div>
				{/if}
				{#if showDepartments}
					<div class="sm:col-span-2">
						<div class="mb-1.5 text-xs font-medium text-muted-foreground">Отделения</div>
						<div class="flex gap-4">
							<div class="flex flex-1 flex-col gap-y-0.5 text-xs">
								{#each deptCols[0] as d (d.label)}
									<button class="flex cursor-pointer gap-1 text-left hover:underline" onclick={() => toggleDept(d.label)}>
										<span class="text-muted-foreground">{deptLabel(d.label)}</span>
										<span class="ml-auto font-semibold tabular-nums">{d.count.toLocaleString('ru-RU')}</span>
									</button>
								{/each}
							</div>
							<div class="flex flex-1 flex-col gap-y-0.5 text-xs">
								{#each deptCols[1] as d (d.label)}
									<button class="flex cursor-pointer gap-1 text-left hover:underline" onclick={() => toggleDept(d.label)}>
										<span class="text-muted-foreground">{deptLabel(d.label)}</span>
										<span class="ml-auto font-semibold tabular-nums">{d.count.toLocaleString('ru-RU')}</span>
									</button>
								{/each}
							</div>
						</div>
					</div>
				{:else}
					<div>
						<div class="mb-1.5 text-xs font-medium text-muted-foreground">Исполнители</div>
						<div class="flex flex-col gap-y-0.5 text-xs">
							{#each stats?.executors ?? [] as ex (ex.label)}
								<button class="flex cursor-pointer gap-1 text-left hover:underline" onclick={() => toggleExecutor(ex.label)}>
									<span class="text-muted-foreground">{ex.label}</span>
									<span class="ml-auto font-semibold tabular-nums">{ex.count.toLocaleString('ru-RU')}</span>
								</button>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
	<div class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border bg-card">
		<Table containerClass="min-h-0 flex-1 overflow-auto">
				<TableHeader>
					<TableRow class="hover:bg-transparent">
						<TableHead class="sticky top-0 z-10 w-8 bg-muted text-center">
							<input
								type="checkbox"
								class="size-4 cursor-pointer accent-primary"
								checked={allSelected}
								disabled={selectingAll}
								onchange={toggleAllVisible}
							/>
						</TableHead>
						{#each VISIBLE_COLUMNS as col (col.key)}
							{@const Icon = HEADER_ICONS[col.key]}
							<TableHead
								class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted text-center"
								onclick={() => setSort(col.key)}
							>
								{#if Icon}
									<span class="inline-flex items-center justify-center" title={col.header}>
										<Icon class="size-4" />
									</span>
								{:else}
									{col.header}
								{/if}
								{sortIndicator(col.key)}
							</TableHead>
						{/each}
					</TableRow>
				</TableHeader>
				<TableBody>
					{#if isPending}
						{#each Array(8) as _}
							<TableRow>
								<TableCell><Skeleton class="h-4 w-4" /></TableCell>
								{#each VISIBLE_COLUMNS as _}
									<TableCell><Skeleton class="h-4 w-full" /></TableCell>
								{/each}
							</TableRow>
						{/each}
					{:else if rows.length === 0}
						<TableRow>
							<TableCell colspan={VISIBLE_COLUMNS.length + 1} class="h-24 text-center text-muted-foreground">
								Нет данных
							</TableCell>
						</TableRow>
					{:else}
						{#each table.getRowModel().rows as row (row.id)}
							{@const id = row.original.task_number ?? ''}
							<TableRow
								class="cursor-pointer"
								title="ПКМ — скопировать номер задания"
								onclick={() => toggleExpanded(id)}
								oncontextmenu={(e) => {
									e.preventDefault();
									copyTask(id);
								}}
							>
								<TableCell class="w-8 text-center" onclick={(e) => e.stopPropagation()}>
									<input
										type="checkbox"
										class="size-4 cursor-pointer accent-primary"
										checked={selected.has(id)}
										onchange={() => toggleSelected(id)}
									/>
								</TableCell>
								{#each row.getAllCells() as cell (cell.id)}
									<TableCell class={cell.column.id === 'norm' ? 'whitespace-nowrap text-center text-sm' : 'whitespace-nowrap text-sm'}>
										{#if cell.column.id === 'reestr_number'}
											{#if cell.getValue() === 'Отклонён'}
												<span class="font-bold text-brand-reestr-rejected">Р</span>
											{:else if cell.getValue()}
												<span class="font-bold text-brand-brown">Р</span>
											{:else}
												-
											{/if}
										{:else if cell.column.id === 'errors'}
											{#if cell.getValue()}
												<span class="font-bold text-destructive">О</span>
											{:else}
												-
											{/if}
										{:else}
											{cell.getValue() ?? ''}
										{/if}
									</TableCell>
								{/each}
							</TableRow>
							{#if expanded.has(id)}
								<TableRow class="bg-muted hover:bg-muted">
									<TableCell colspan={VISIBLE_COLUMNS.length + 1}>
										<div class="grid grid-cols-1 gap-x-6 gap-y-4 py-2 sm:grid-cols-2 lg:grid-cols-4">
											{#each EXPAND_GROUPS as group (group.title)}
												<div class="space-y-2">
													{#each group.columns as c (c.key)}
														<div class="text-sm">
															<span class="text-muted-foreground">{c.header}:</span>{' '}
															<span>{row.original[c.key] || '-'}</span>
														</div>
													{/each}
												</div>
											{/each}
										</div>
										<div class="mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
											{#if row.original.reestr_number && row.original.reestr_number !== 'Отклонён'}
												<Button
													size="sm"
													variant="destructive"
													onclick={() => resetReestr(row.original)}
												>
													<Trash2 class="size-4" />
													Удалить из реестра
												</Button>
											{#if canSelectForReestr}
												<Button
													size="sm"
													variant="outline"
													onclick={() => window.open(downloadReestrUrl(row.original.reestr_number!), '_blank')}
												>
													<Printer class="size-4" />
													Печать реестра
												</Button>
											{/if}

											{/if}
											{#if canChangeReport}
												<select
													class="h-8 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring"
													value={reportChoice[id] ?? ''}
													onchange={(e) =>
														(reportChoice[id] = (e.currentTarget as HTMLSelectElement).value)}
												>
													<option value="" disabled>Заменить вид работ</option>
													<option value="__none__">Не выполнено</option>
													{#each reportOptions as r (r)}
														<option value={r}>{r}</option>
													{/each}
												</select>
												<Button
													size="sm"
													variant="default"
													disabled={!reportChoice[id]}
													onclick={() => changeReport(row.original)}
												>
													Заменить
												</Button>
											{/if}
										</div>
									</TableCell>
								</TableRow>
							{/if}
						{/each}
					{/if}
				</TableBody>
			</Table>
	</div>

	<div class="flex items-center justify-between gap-3">
		<span class="text-sm text-muted-foreground">
			Всего: {total.toLocaleString('ru-RU')}
			{#if selected.size > 0}
				· Выбрано: {selected.size}
			{/if}
		</span>
		<div class="flex flex-wrap items-center gap-1">
			<Button variant="outline" size="sm" disabled={page <= 1} onclick={() => goToPage(1)} aria-label="Первая страница">
				<ChevronsLeft class="size-4" />
			</Button>
			<Button variant="outline" size="sm" disabled={page <= 1} onclick={() => goToPage(page - 1)} aria-label="Назад">
				<ChevronLeft class="size-4" />
			</Button>
			{#each pageItems(page, totalPages) as item, i (i)}
				{#if item === '…'}
					<span class="px-1 text-sm text-muted-foreground">…</span>
				{:else}
					<Button
						variant={item === page ? 'default' : 'outline'}
						size="sm"
						onclick={() => goToPage(item)}
					>
						{item}
					</Button>
				{/if}
			{/each}
			<Button variant="outline" size="sm" disabled={page >= totalPages} onclick={() => goToPage(page + 1)} aria-label="Вперёд">
				<ChevronRight class="size-4" />
			</Button>
			<Button variant="outline" size="sm" disabled={page >= totalPages} onclick={() => goToPage(totalPages)} aria-label="Последняя страница">
				<ChevronsRight class="size-4" />
			</Button>
		</div>
	</div>
</div>
