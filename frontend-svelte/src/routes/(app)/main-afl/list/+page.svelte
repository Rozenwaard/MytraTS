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
		fetchReestrList,
		findReestr,
		downloadReestrUrl,
		fetchAllTaskNumbers,
		resetReestr,
		type MainAflRow,
		type MainAflResponse
	} from '$lib/api/main-afl';
	import { VISIBLE_COLUMNS } from '$lib/columns';
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
	import ChevronsLeft from '@lucide/svelte/icons/chevrons-left';
	import ChevronsRight from '@lucide/svelte/icons/chevrons-right';
	import ListChecks from '@lucide/svelte/icons/list-checks';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import Coins from '@lucide/svelte/icons/coins';
	import type { Component } from 'svelte';
	import { Input } from '$lib/components/ui/input';
	import { queryClient } from '$lib/query';
	import { toast } from '$lib/store/toast.svelte';
	import { copyText } from '$lib/clipboard';

	const NO_REESTR = '__none__';

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
	let selected = $state<Set<string>>(new Set());
	let allSelected = $state(false);
	let selectingAll = $state(false);

	let reestrs = $state<string[]>([]);
	let meta = $state<Record<string, { task_report: string | null; customer: string | null }>>({});
	let activeReestr = $state('');
	let emptyReestrs = $state<Set<string>>(new Set());
	let reestrFilter = $state<string | undefined>(undefined);
	let exact = $state<string | undefined>(undefined);

	let searchQ = $state('');
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		fetchReestrList()
			.then((d) => {
				reestrs = d.reestrs;
				meta = d.meta;
				if (d.reestrs.length > 0 && !activeReestr) {
					activeReestr = d.reestrs[0];
					reestrFilter = d.reestrs[0];
				}
			})
			.catch(() => {});
	});

	const sortKey = $derived(sorting[0]?.id ?? '');
	const sortOrder = $derived(sorting[0]?.desc ? 'desc' : 'asc');

	const query = createQuery<MainAflResponse>(
		toStore(() => ({
			queryKey: ['main-afl', 'list', page, sortKey, sortOrder, reestrFilter, exact],
			queryFn: () =>
				api<MainAflResponse>(
					`/api/main-afl?${buildMainAflQuery({
						page,
						per_page: perPage,
						sort: sortKey || undefined,
						order: sortKey ? sortOrder : undefined,
						reestr: reestrFilter || undefined,
						exact: exact || undefined
					})}`
				)
		}))
	);

	const result = fromStore(query);
	const rows = $derived(result.current.data?.rows ?? []);
	const isPending = $derived(result.current.isPending);
	const total = $derived(result.current.data?.total ?? 0);
	const totalPages = $derived(Math.max(1, Math.ceil(total / perPage)));

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

	function currentFilterParams() {
		return {
			reestr: reestrFilter || undefined,
			exact: exact || undefined
		};
	}
	const activeMeta = $derived(meta[activeReestr]);

	function toggleSelected(id: string) {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
		allSelected = false;
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
				toast(ids.length ? `Выбрано: ${ids.length}` : 'Нет строк в текущем фильтре');
			}
		} catch {
			toast('Ошибка выбора строк');
		} finally {
			selectingAll = false;
		}
	}

	$effect(() => {
		// сброс «выбрано всё» при смене фильтра
		reestrFilter;
		exact;
		allSelected = false;
	});

	async function copyTask(id: string) {
		if (id) await copyText(id);
	}

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
		const res: (number | '…')[] = [];
		let prev = 0;
		for (const n of sorted) {
			if (n - prev > 1) res.push('…');
			res.push(n);
			prev = n;
		}
		return res;
	}

	function selectReestr(rn: string) {
		if (debounceTimer) clearTimeout(debounceTimer);
		searchQ = '';
		activeReestr = rn;
		reestrFilter = rn;
		exact = undefined;
		page = 1;
	}

	async function handleSearch(q: string) {
		if (!q) {
			reestrFilter = activeReestr || reestrs[0] || undefined;
			exact = undefined;
			page = 1;
			return;
		}
		const rn = await findReestr(q);
		if (rn) {
			activeReestr = rn;
			reestrFilter = rn;
			exact = q;
		} else {
			reestrFilter = NO_REESTR;
			exact = undefined;
		}
		page = 1;
	}

	function toggleEmpty(rn: string) {
		const next = new Set(emptyReestrs);
		if (next.has(rn)) next.delete(rn);
		else next.add(rn);
		emptyReestrs = next;
	}

	async function handleReset() {
		if (selected.size === 0) {
			toast('Не выбраны строки');
			return;
		}
		try {
			const result = await resetReestr([...selected]);
			toast(`Сброшено: ${result.cleared}`);
			selected = new Set();
			allSelected = false;
			queryClient.invalidateQueries({ queryKey: ['main-afl'] });
			fetchReestrList()
				.then((d) => {
					reestrs = d.reestrs;
					meta = d.meta;
				})
				.catch(() => {});
		} catch {
			toast('Ошибка сброса реестра');
		}
	}
</script>

<div class="flex h-full flex-col gap-3 p-3">
	<div class="shrink-0 space-y-2">
		<div class="flex flex-wrap gap-2 items-center">
			{#each reestrs as rn (rn)}
				<button
					class={activeReestr === rn
						? 'rounded bg-primary px-2 py-0.5 text-sm text-primary-foreground'
						: 'rounded bg-muted px-2 py-0.5 text-sm hover:bg-muted/70'}
					onclick={() => selectReestr(rn)}
				>
					{rn}{emptyReestrs.has(rn) ? ' (П)' : ''}
				</button>
			{/each}
		</div>
		<div class="flex flex-wrap gap-3 items-center">
			<Input
				placeholder="№ задания / л/с"
				class="w-56"
				bind:value={searchQ}
				oninput={(e) => {
					const v = (e.currentTarget as HTMLInputElement).value;
					if (debounceTimer) clearTimeout(debounceTimer);
					debounceTimer = setTimeout(() => handleSearch(v.trim()), 300);
				}}
			/>
			<Button
				variant="outline"
				size="sm"
				onclick={() => {
					if (debounceTimer) clearTimeout(debounceTimer);
					searchQ = '';
					handleSearch('');
				}}
			>
				Сброс
			</Button>
			<Button
				variant="outline"
				size="sm"
				onclick={() => activeReestr && window.open(downloadReestrUrl(activeReestr), '_blank')}
			>
				Печать
			</Button>
			<Button variant="outline" size="sm" onclick={() => activeReestr && toggleEmpty(activeReestr)}>
				{activeReestr && emptyReestrs.has(activeReestr) ? 'Снять (П)' : 'Пустой'}
			</Button>
			<Button variant="outline" size="sm" onclick={handleReset}>Удалить из реестра</Button>
			{#if activeMeta}
				<span class="text-xs text-muted-foreground">|</span>
				<span class="text-xs text-muted-foreground">
					Вид работ: <span class="text-foreground">{activeMeta.task_report ?? '—'}</span>
				</span>
				<span class="text-xs text-muted-foreground">
					Заказчик: <span class="text-foreground">{activeMeta.customer ?? '—'}</span>
				</span>
			{/if}
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
