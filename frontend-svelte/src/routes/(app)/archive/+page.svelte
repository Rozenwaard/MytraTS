<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { createTable, getCoreRowModel, type ColumnDef } from '@tanstack/table-core';
	import {
		fetchStoryAfl,
		rejectStoryRows,
		type StoryAflResponse,
		type StoryAflRow
	} from '$lib/api/story';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import ChevronsLeft from '@lucide/svelte/icons/chevrons-left';
	import ChevronsRight from '@lucide/svelte/icons/chevrons-right';
	import { queryClient } from '$lib/query';
	import { toast } from '$lib/store/toast.svelte';
	import { auth } from '$lib/store/auth.svelte';

	const ARCHIVE_COLUMNS: { key: keyof StoryAflRow; header: string }[] = [
		{ key: 'task_number', header: 'Номер задания' },
		{ key: 'created_at', header: 'Создано' },
		{ key: 'customer', header: 'Заказчик' },
		{ key: 'task_report', header: 'Вид работ' },
		{ key: 'personal_account', header: 'Точка учёта' },
		{ key: 'address', header: 'Адрес' },
		{ key: 'municipal_district', header: 'Район' },
		{ key: 'executor', header: 'Исполнитель' },
		{ key: 'executor_organization', header: 'Организация' },
		{ key: 'done_day', header: 'Дата' },
		{ key: 'reestr_number', header: 'Реестр' },
		{ key: 'report', header: 'Отчёт' }
	];

	const columns: ColumnDef<StoryAflRow>[] = ARCHIVE_COLUMNS.map((c) => ({
		accessorKey: c.key,
		header: c.header
	}));

	const FILTER_FIELDS: { key: keyof StoryAflRow; label: string }[] = [
		{ key: 'customer', label: 'Заказчик' },
		{ key: 'task_report', label: 'Вид работ' },
		{ key: 'task_type', label: 'Вид задания' },
		{ key: 'grid', label: 'Сеть' },
		{ key: 'house_type', label: 'Тип дома' },
		{ key: 'municipal_district', label: 'Район' },
		{ key: 'executor_organization', label: 'Организация' },
		{ key: 'report', label: 'Отчёт' }
	];

	const canReject = $derived(auth.user?.role === 'администратор' || auth.user?.role === 'специалист');

	const perPage = 50;
	let page = $state(1);
	let selected = $state<Set<string>>(new Set());
	let searchQ = $state('');
	let search = $state('');
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;
	let periodMonth = $state('');
	let periodYear = $state('');
	let filters = $state<Record<string, string>>({});

	const query = createQuery<StoryAflResponse>(
		toStore(() => ({
			queryKey: ['story-afl', page, search, periodMonth, periodYear, filters],
			queryFn: () =>
				fetchStoryAfl({
					page,
					per_page: perPage,
					search: search || undefined,
					period_month: periodMonth || undefined,
					period_year: periodYear || undefined,
					customer: filters.customer || undefined,
					task_report: filters.task_report || undefined,
					task_type: filters.task_type || undefined,
					grid: filters.grid || undefined,
					house_type: filters.house_type || undefined,
					municipal_district: filters.municipal_district || undefined,
					executor_organization: filters.executor_organization || undefined,
					report: filters.report || undefined
				})
		}))
	);

	const result = fromStore(query);
	const rows = $derived(result.current.data?.rows ?? []);
	const isPending = $derived(result.current.isPending);
	const total = $derived(result.current.data?.total ?? 0);
	const totalPages = $derived(Math.max(1, Math.ceil(total / perPage)));
	const filterCounts = $derived(result.current.data?.filter_counts ?? {});

	const table = $derived(
		createTable({
			data: rows,
			columns,
			onStateChange: () => {},
			renderFallbackValue: null,
			getCoreRowModel: getCoreRowModel(),
			manualPagination: true,
			state: {}
		})
	);
	function toggleSelected(id: string) {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
	}

	function onSearchInput(e: Event) {
		const v = (e.currentTarget as HTMLInputElement).value;
		searchQ = v;
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			search = v.trim();
			page = 1;
		}, 300);
	}

	function setFilter(field: string, value: string) {
		filters = { ...filters, [field]: value };
		page = 1;
	}

	function resetFilters() {
		searchQ = '';
		search = '';
		periodMonth = '';
		periodYear = '';
		filters = {};
		page = 1;
	}

	async function handleReject() {
		if (selected.size === 0) {
			toast('Не выбраны строки');
			return;
		}
		try {
			const res = await rejectStoryRows([...selected]);
			toast(`Отклонено: ${res.updated}`);
			selected = new Set();
			queryClient.invalidateQueries({ queryKey: ['story-afl'] });
		} catch {
			toast('Ошибка отклонения строк');
		}
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
</script>

<div class="flex h-full flex-col gap-3 p-3">
	<div class="shrink-0 space-y-2">
		<div class="flex flex-wrap items-center gap-2">
			<Input
				placeholder="№ задания / л/с / адрес"
				class="w-56"
				bind:value={searchQ}
				oninput={onSearchInput}
			/>
			<Input
				type="number"
				placeholder="Месяц"
				class="w-20"
				bind:value={periodMonth}
				onchange={() => (page = 1)}
			/>
			<Input
				type="number"
				placeholder="Год"
				class="w-24"
				bind:value={periodYear}
				onchange={() => (page = 1)}
			/>
			{#each FILTER_FIELDS as f (f.key)}
				<select
					class="h-9 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring"
					value={filters[f.key] ?? ''}
					onchange={(e) => setFilter(f.key, (e.currentTarget as HTMLSelectElement).value)}
				>
					<option value="">{f.label}: все</option>
					{#each filterCounts[f.key] ?? [] as opt (opt.value)}
						<option value={opt.value === '(пусто)' ? '' : opt.value}>
							{opt.value} ({opt.count})
						</option>
					{/each}
				</select>
			{/each}
			<Button variant="outline" size="sm" onclick={resetFilters}>Сброс</Button>
			{#if canReject}
				<Button variant="destructive" size="sm" disabled={selected.size === 0} onclick={handleReject}>
					Отклонить
				</Button>
			{/if}
		</div>
	</div>

	<div class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border bg-card">
		<Table containerClass="min-h-0 flex-1 overflow-auto">
			<TableHeader>
				<TableRow class="hover:bg-transparent">
					<TableHead class="sticky top-0 z-10 w-8 bg-muted text-center"></TableHead>
					{#each ARCHIVE_COLUMNS as col (col.key)}
						<TableHead class="sticky top-0 z-10 whitespace-nowrap bg-muted text-center">
							{col.header}
						</TableHead>
					{/each}
				</TableRow>
			</TableHeader>
			<TableBody>
				{#if isPending}
					{#each Array(8) as _}
						<TableRow>
							<TableCell><Skeleton class="h-4 w-4" /></TableCell>
							{#each ARCHIVE_COLUMNS as _}
								<TableCell><Skeleton class="h-4 w-full" /></TableCell>
							{/each}
						</TableRow>
					{/each}
				{:else if rows.length === 0}
					<TableRow>
						<TableCell colspan={ARCHIVE_COLUMNS.length + 1} class="h-24 text-center text-muted-foreground">
							Нет данных
						</TableCell>
					</TableRow>
				{:else}
					{#each table.getRowModel().rows as row (row.id)}
						{@const id = row.original.task_number ?? ''}
						<TableRow>
							<TableCell class="w-8 text-center">
								<input
									type="checkbox"
									class="size-4 cursor-pointer accent-primary"
									checked={selected.has(id)}
									onchange={() => toggleSelected(id)}
								/>
							</TableCell>
							{#each row.getAllCells() as cell (cell.id)}
								<TableCell class="whitespace-nowrap text-sm">
									{cell.getValue() ?? ''}
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

