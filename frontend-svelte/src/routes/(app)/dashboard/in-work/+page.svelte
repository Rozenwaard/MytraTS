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
	import { fetchInWork, fetchInWorkStats, type InWorkStats } from '$lib/api/dashboard';
	import type { MainAflRow, MainAflResponse } from '$lib/api/main-afl';
	import { EXPAND_GROUPS, type ColumnMeta } from '$lib/columns';
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
	import { Input } from '$lib/components/ui/input';
	import Search from '@lucide/svelte/icons/search';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import ChevronsLeft from '@lucide/svelte/icons/chevrons-left';
	import ChevronsRight from '@lucide/svelte/icons/chevrons-right';
	import { copyText } from '$lib/clipboard';
	import { auth } from '$lib/store/auth.svelte';

	const IN_WORK_COLUMNS: ColumnMeta[] = [
		{ key: 'customer', header: 'Заказчик' },
		{ key: 'work_type_in_task', header: 'Поручение' },
		{ key: 'personal_account', header: 'Точка учёта' },
		{ key: 'address', header: 'Адрес' },
		{ key: 'executor_organization', header: 'Отделение' },
		{ key: 'executor', header: 'Исполнитель' }
	];
	const IN_WORK_EXPAND_GROUPS = EXPAND_GROUPS.map((g) => {
		const columns = g.columns.filter(
			(c) =>
				c.key !== 'reestr_number' &&
				c.key !== 'errors' &&
				c.key !== 'task_output' &&
				c.key !== 'task_detail'
		);
		if (g.title === 'Задание') {
			columns.push({ key: 'status', header: 'Статус задания' });
			columns.push({ key: 'due_date', header: 'Выполнить до' });
		}
		return { ...g, columns };
	});

	const columns: ColumnDef<MainAflRow>[] = IN_WORK_COLUMNS.map((c) => ({
		accessorKey: c.key,
		header: c.header
	}));

	const perPage = 50;
	let page = $state(1);
	let sorting = $state<SortingState>([]);
	let expanded = $state<Set<string>>(new Set());

	let searchInput = $state('');
	let searchValue = $state('');
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		const value = searchInput;
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			searchValue = value;
		}, 300);
	});

	let stats = $state<InWorkStats | null>(null);
	let customer = $state<string | undefined>(undefined);
	let taskType = $state<string | undefined>(undefined);
	let revoked = $state(false);
	let queue = $state<string | undefined>(undefined);
	let status = $state<string | undefined>(undefined);
	let executorOrg = $state('');

	const isFieldRole = $derived(auth.user?.role === 'оператор' || auth.user?.role === 'работник');
	const isAdmin = $derived(auth.user?.role === 'администратор');

	// Ширина дропдауна отделений фиксируется по самой широкой надписи (название + счётчик),
	// чтобы список не «прыгал» при смене фильтров (счётчики меняют длину).
	const deptSelectWidth = $derived(() => {
		const names = ['Все отделения', ...(stats?.depts ?? []).map((d) => d.label)];
		const maxName = names.reduce((m, n) => (n.length > m ? n.length : m), 0);
		// « (999 999)» — счётчик с разделителем тысяч + скобки, плюс запас на паддинг/стрелку.
		return `${maxName + 12}ch`;
	});

	let statsReq = 0;
	$effect(() => {
		const req = ++statsReq;
		fetchInWorkStats({
			customer,
			task_type: taskType,
			revoked: revoked || undefined,
			queue: queue || undefined,
			status: status || undefined,
			executor_org: executorOrg || undefined
		})
			.then((s) => {
				if (req === statsReq) stats = s;
			})
			.catch(() => {});
	});

	// Колонки-фильтры (Статистика / Очередь / Статусы) — взаимоисключающие:
	// активна только одна; отделение суммируется с ней.
	function toggleStat(label: string) {
		let nextCustomer: string | undefined;
		let nextTaskType: string | undefined;
		let nextRevoked = false;
		if (label === 'ПСК') nextCustomer = customer === 'ПСК' ? undefined : 'ПСК';
		else if (label === 'РЛЭ') nextCustomer = customer === 'РЛЭ' ? undefined : 'РЛЭ';
		else if (label === 'План') nextTaskType = taskType === 'Плановый' ? undefined : 'Плановый';
		else if (label === 'Внеплан') nextTaskType = taskType === 'Внеплановый' ? undefined : 'Внеплановый';
		else if (label === 'Отозвано') nextRevoked = !revoked;
		customer = nextCustomer;
		taskType = nextTaskType;
		revoked = nextRevoked;
		queue = undefined;
		status = undefined;
		page = 1;
	}

	function toggleQueue(value: string) {
		queue = queue === value ? undefined : value;
		customer = undefined;
		taskType = undefined;
		revoked = false;
		status = undefined;
		page = 1;
	}

	function toggleStatus(label: string) {
		status = status === label ? undefined : label;
		customer = undefined;
		taskType = undefined;
		revoked = false;
		queue = undefined;
		page = 1;
	}

	function resetFilters() {
		searchInput = '';
		searchValue = '';
		customer = undefined;
		taskType = undefined;
		revoked = false;
		queue = undefined;
		status = undefined;
		executorOrg = '';
		page = 1;
	}

	const sortKey = $derived(sorting[0]?.id ?? '');
	const sortOrder = $derived(sorting[0]?.desc ? 'desc' : 'asc');

	const query = createQuery<MainAflResponse>(
		toStore(() => ({
			queryKey: ['dashboard-in-work', page, sortKey, sortOrder, searchValue, customer, taskType, revoked, queue, status, executorOrg],
			queryFn: () =>
				fetchInWork({
					page,
					per_page: perPage,
					sort: sortKey || undefined,
					order: sortKey ? sortOrder : undefined,
					search: searchValue || undefined,
					customer,
					task_type: taskType,
					revoked: revoked || undefined,
					queue: queue || undefined,
					status: status || undefined,
					executor_org: executorOrg || undefined
				})
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

	async function copyTask(id: string) {
		if (id) await copyText(id);
	}
</script>

<div class="flex h-full flex-col gap-3 p-3">
	<div class="shrink-0 space-y-3">
		<div class="rounded-md border bg-card p-3">
			<div class="flex flex-wrap items-center gap-3">
				<div class="relative w-full max-w-sm">
					<Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
					<Input bind:value={searchInput} placeholder="Поиск по адресу, № задания или л/с" class="bg-background pl-8" />
				</div>
				{#if !isFieldRole}
					<select
						class="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
						style={`min-width: ${deptSelectWidth}`}
						bind:value={executorOrg}
					>
						<option value="">Все отделения</option>
						{#each stats?.depts ?? [] as d (d.label)}
							<option value={d.label}>{d.label} ({d.count.toLocaleString('ru-RU')})</option>
						{/each}
					</select>
				{/if}
				<Button variant="outline" size="sm" onclick={resetFilters}>Сброс фильтров</Button>
				{#if isAdmin}
					<Button variant="outline" size="sm" onclick={() => window.open('/api/dashboard/in-work/unenriched-report', '_blank')}>
						Не обогащено{stats ? ` (${stats.unenriched})` : ''}
					</Button>
				{/if}
			</div>
		</div>

		<div class="rounded-md border bg-card p-3">
			<div class="grid grid-cols-1 gap-6 text-sm sm:grid-cols-3">
				<div>
					<div class="mb-1.5 text-xs font-medium text-muted-foreground">Статистика</div>
					<div class="flex flex-col gap-y-0.5 text-xs">
						{#each [
							{ label: 'ПСК', count: stats?.customers?.['ПСК'], active: customer === 'ПСК' },
							{ label: 'РЛЭ', count: stats?.customers?.['РЛЭ'], active: customer === 'РЛЭ' },
							{ label: 'План', count: stats?.plan, active: taskType === 'Плановый' },
							{ label: 'Внеплан', count: stats?.unplan, active: taskType === 'Внеплановый' },
							{ label: 'Отозвано', count: stats?.revoked, active: revoked }
						] as s (s.label)}
							<button class="flex cursor-pointer gap-1 rounded px-1 -mx-1 text-left hover:underline {s.active ? 'bg-primary/15' : ''}" onclick={() => toggleStat(s.label)}>
								<span class={s.active ? 'text-primary' : 'text-muted-foreground'}>{s.label}</span>
								<span class="ml-auto font-semibold tabular-nums {s.active ? 'text-primary' : ''}">{s.count != null ? s.count.toLocaleString('ru-RU') : '—'}</span>
							</button>
						{/each}
					</div>
				</div>
				<div>
					<div class="mb-1.5 text-xs font-medium text-muted-foreground">Очередь</div>
					<div class="flex flex-col gap-y-0.5 text-xs">
						{#each stats?.queue ?? [] as q (q.label)}
							<button class="flex cursor-pointer gap-1 rounded px-1 -mx-1 text-left hover:underline {queue === q.value ? 'bg-primary/15' : ''}" onclick={() => toggleQueue(q.value)}>
								<span class={queue === q.value ? 'text-primary' : 'text-muted-foreground'}>{q.label}</span>
								<span class="ml-auto font-semibold tabular-nums {queue === q.value ? 'text-primary' : ''}">{q.count.toLocaleString('ru-RU')}</span>
							</button>
						{/each}
					</div>
				</div>
				<div>
					<div class="mb-1.5 text-xs font-medium text-muted-foreground">Статусы</div>
					<div class="flex flex-col gap-y-0.5 text-xs">
						{#each stats?.statuses ?? [] as st (st.label)}
							<button class="flex cursor-pointer gap-1 rounded px-1 -mx-1 text-left hover:underline {status === st.label ? 'bg-primary/15' : ''}" onclick={() => toggleStatus(st.label)}>
								<span class={status === st.label ? 'text-primary' : 'text-muted-foreground'}>{st.label}</span>
								<span class="ml-auto font-semibold tabular-nums {status === st.label ? 'text-primary' : ''}">{st.count.toLocaleString('ru-RU')}</span>
							</button>
						{/each}
					</div>
				</div>
			</div>
		</div>
	</div>

	<div class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border bg-card">
		<Table containerClass="min-h-0 flex-1 overflow-auto">
			<TableHeader>
				<TableRow class="hover:bg-transparent">
					{#each IN_WORK_COLUMNS as col (col.key)}
						<TableHead
							class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted text-center"
							onclick={() => setSort(col.key)}
						>
							{col.header}
							{sortIndicator(col.key)}
						</TableHead>
					{/each}
				</TableRow>
			</TableHeader>
			<TableBody>
				{#if isPending}
					{#each Array(8) as _}
						<TableRow>
							{#each IN_WORK_COLUMNS as _}
								<TableCell><Skeleton class="h-4 w-full" /></TableCell>
							{/each}
						</TableRow>
					{/each}
				{:else if rows.length === 0}
					<TableRow>
						<TableCell colspan={IN_WORK_COLUMNS.length} class="h-24 text-center text-muted-foreground">
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
							{#each row.getAllCells() as cell (cell.id)}
								<TableCell class="whitespace-nowrap text-sm">
									{cell.getValue() ?? ''}
								</TableCell>
							{/each}
						</TableRow>
						{#if expanded.has(id)}
							<TableRow class="bg-muted hover:bg-muted">
								<TableCell colspan={IN_WORK_COLUMNS.length}>
									<div class="grid grid-cols-1 gap-x-6 gap-y-4 py-2 sm:grid-cols-2 lg:grid-cols-4">
										{#each IN_WORK_EXPAND_GROUPS as group (group.title)}
											<div class="space-y-2">
												<div class="text-sm font-medium">{group.title}</div>
												{#each group.columns as c (c.key)}
													<div class="text-sm">
														<span class="text-muted-foreground">{c.header}:</span>{' '}
														<span>{row.original[c.key] || '-'}</span>
													</div>
												{/each}
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

	<div class="flex items-center justify-between gap-3">
		<span class="text-sm text-muted-foreground">
			Всего: {total.toLocaleString('ru-RU')}
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

