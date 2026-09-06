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
	import { buildMainAflQuery, type MainAflRow, type MainAflResponse } from '$lib/api/main-afl';
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
	import { queryClient } from '$lib/query';
	import { toast } from '$lib/store/toast.svelte';
	import { auth } from '$lib/store/auth.svelte';

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

	const canChangeReport = $derived(
		auth.user?.role === 'администратор' || auth.user?.role === 'специалист'
	);

	$effect(() => {
		api<string[]>('/api/task-reports')
			.then((list) => (reportOptions = list))
			.catch(() => {});
	});

	const sortKey = $derived(sorting[0]?.id ?? '');
	const sortOrder = $derived(sorting[0]?.desc ? 'desc' : 'asc');

	const query = createQuery<MainAflResponse>(
		toStore(() => ({
			queryKey: ['main-afl', page, sortKey, sortOrder, searchValue],
			queryFn: () =>
				api<MainAflResponse>(
					`/api/main-afl?${buildMainAflQuery({
						page,
						per_page: perPage,
						sort: sortKey || undefined,
						order: sortKey ? sortOrder : undefined,
						search: searchValue || undefined
					})}`
				)
		}))
	);

	const result = fromStore(query);
	const rows = $derived(result.current.data?.rows ?? []);
	const isPending = $derived(result.current.isPending);

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

<div class="flex h-full flex-col gap-3">
	<div class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border">
		<Table containerClass="min-h-0 flex-1 overflow-auto">
				<TableHeader>
					<TableRow class="hover:bg-transparent">
						{#each VISIBLE_COLUMNS as col (col.key)}
							{@const Icon = HEADER_ICONS[col.key]}
							<TableHead
								class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-background text-center"
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
								{#each VISIBLE_COLUMNS as _}
									<TableCell><Skeleton class="h-4 w-full" /></TableCell>
								{/each}
							</TableRow>
						{/each}
					{:else if rows.length === 0}
						<TableRow>
							<TableCell colspan={VISIBLE_COLUMNS.length} class="h-24 text-center text-muted-foreground">
								Нет данных
							</TableCell>
						</TableRow>
					{:else}
						{#each table.getRowModel().rows as row (row.id)}
							{@const id = row.original.task_number ?? ''}
							<TableRow class="cursor-pointer" onclick={() => toggleExpanded(id)}>
								{#each row.getAllCells() as cell (cell.id)}
									<TableCell class="whitespace-nowrap text-sm">
										{#if cell.column.id === 'reestr_number'}
											{cell.getValue() ? 'Р' : '-'}
										{:else if cell.column.id === 'errors'}
											{cell.getValue() ? 'О' : '-'}
										{:else}
											{cell.getValue() ?? ''}
										{/if}
									</TableCell>
								{/each}
							</TableRow>
							{#if expanded.has(id)}
								<TableRow class="bg-muted/40 hover:bg-muted/40">
									<TableCell colspan={VISIBLE_COLUMNS.length}>
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
													variant="outline"
													onclick={() => resetReestr(row.original)}
												>
													<Trash2 class="size-4" />
													Удалить из реестра
												</Button>
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
													variant="outline"
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
		<span class="text-sm text-muted-foreground">Всего: {total.toLocaleString('ru-RU')}</span>
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
