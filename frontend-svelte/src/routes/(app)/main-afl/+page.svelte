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
	import { VISIBLE_COLUMNS, EXPAND_COLUMNS } from '$lib/columns';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';

	const columns: ColumnDef<MainAflRow>[] = VISIBLE_COLUMNS.map((c) => ({
		accessorKey: c.key,
		header: c.header
	}));

	const perPage = 50;
	let page = $state(1);
	let sorting = $state<SortingState>([]);
	let selected = $state<Set<string>>(new Set());
	let expanded = $state<Set<string>>(new Set());

	const sortKey = $derived(sorting[0]?.id ?? '');
	const sortOrder = $derived(sorting[0]?.desc ? 'desc' : 'asc');

	const query = createQuery<MainAflResponse>(
		toStore(() => ({
			queryKey: ['main-afl', page, sortKey, sortOrder],
			queryFn: () =>
				api<MainAflResponse>(
					`/api/main-afl?${buildMainAflQuery({
						page,
						per_page: perPage,
						sort: sortKey || undefined,
						order: sortKey ? sortOrder : undefined
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

	function toggleSelected(id: string) {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
	}

	function toggleExpanded(id: string) {
		const next = new Set(expanded);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		expanded = next;
	}

	function toggleSelectAll() {
		if (selected.size === rows.length && rows.length > 0) {
			selected = new Set();
		} else {
			selected = new Set(rows.map((r) => r.task_number ?? '').filter(Boolean));
		}
	}

	function goToPage(p: number) {
		if (p >= 1 && p <= totalPages) page = p;
	}
</script>

<div class="flex h-full flex-col gap-3">
	<div class="rounded-md border">
		<div class="overflow-auto">
			<Table>
				<TableHeader>
					<TableRow class="hover:bg-transparent">
						<TableHead class="w-10">
							<Checkbox
								checked={rows.length > 0 && selected.size === rows.length}
								onclick={toggleSelectAll}
								aria-label="Выбрать все"
							/>
						</TableHead>
						{#each VISIBLE_COLUMNS as col (col.key)}
							<TableHead
								class="cursor-pointer select-none whitespace-nowrap text-center"
								onclick={() => setSort(col.key)}
							>
								{col.header}{sortIndicator(col.key)}
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
							<TableRow class="cursor-pointer" onclick={() => toggleExpanded(id)}>
								<TableCell onclick={(e) => e.stopPropagation()}>
									<Checkbox checked={selected.has(id)} onclick={() => toggleSelected(id)} aria-label="Выбрать строку" />
								</TableCell>
								{#each row.getVisibleCells() as cell (cell.id)}
									<TableCell class="whitespace-nowrap text-sm">{cell.getValue() ?? ''}</TableCell>
								{/each}
							</TableRow>
							{#if expanded.has(id)}
								<TableRow class="bg-muted/40 hover:bg-muted/40">
									<TableCell colspan={VISIBLE_COLUMNS.length + 1}>
										<div class="grid grid-cols-2 gap-x-6 gap-y-2 py-2 md:grid-cols-3 lg:grid-cols-4">
											{#each EXPAND_COLUMNS as c (c.key)}
												<div class="text-sm">
													<span class="text-muted-foreground">{c.header}:</span>{' '}
													<span>{row.original[c.key] ?? '—'}</span>
												</div>
											{/each}
										</div>
									</TableCell>
								</TableRow>
							{/if}
						{/each}
					{/if}
				</TableBody>
			</Table>
		</div>
	</div>

	<div class="flex items-center justify-between">
		<span class="text-sm text-muted-foreground">Всего: {total.toLocaleString('ru-RU')}</span>
		<div class="flex items-center gap-2">
			<Button variant="outline" size="sm" disabled={page <= 1} onclick={() => goToPage(page - 1)} aria-label="Назад">
				<ChevronLeft class="size-4" />
			</Button>
			<span class="text-sm">Стр. {page} из {totalPages}</span>
			<Button variant="outline" size="sm" disabled={page >= totalPages} onclick={() => goToPage(page + 1)} aria-label="Вперёд">
				<ChevronRight class="size-4" />
			</Button>
		</div>
	</div>
</div>
