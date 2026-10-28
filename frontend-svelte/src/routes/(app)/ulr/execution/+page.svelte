<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { queryClient } from '$lib/query';
	import { fetchUlrExecution, updateUlrExecution, type UlrExecutionRow } from '$lib/api/ulr';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { toast } from '$lib/store/toast.svelte';
	import { copyText } from '$lib/clipboard';
	import Coins from '@lucide/svelte/icons/coins';
	import ListChecks from '@lucide/svelte/icons/list-checks';
	import type { Component } from 'svelte';

	const HEADER_ICONS: Partial<Record<keyof UlrExecutionRow, Component>> = {
		reestr_number: ListChecks,
		norm: Coins
	};

	const COLUMNS: { key: keyof UlrExecutionRow; header: string }[] = [
		{ key: 'customer', header: 'Заказчик' },
		{ key: 'work_type_in_task', header: 'Поручение' },
		{ key: 'due_date', header: 'Завершить' },
		{ key: 'subscriber_name', header: 'Потребитель' },
		{ key: 'address', header: 'Адрес' },
		{ key: 'status', header: 'Статус задания' },
		{ key: 'reestr_number', header: 'Реестр' },
		{ key: 'norm', header: 'Норматив' }
	];

	type FieldDef = {
		key: keyof UlrExecutionRow;
		label: string;
		edit?: 'executor' | 'work' | 'date' | 'co' | 'checkbox';
	};

	const GROUPS: { title: string; fields: FieldDef[] }[] = [
		{
			title: 'Задание',
			fields: [
				{ key: 'task_number', label: 'Номер задания' },
				{ key: 'created_at', label: 'Создано' },
				{ key: 'visit_reason', label: 'Основание' },
				{ key: 'task_type', label: 'Вид задания' }
			]
		},
		{
			title: 'Потребитель',
			fields: [
				{ key: 'personal_account', label: 'Точка учёта' },
				{ key: 'service_object_type', label: 'Объект' },
				{ key: 'grid', label: 'Сеть' },
				{ key: 'subscriber_type', label: 'Тип потребителя' }
			]
		},
		{
			title: 'ПУ',
			fields: [
				{ key: 'meter_model', label: 'Модель ПУ' },
				{ key: 'meter_type', label: 'Тип ПУ' },
				{ key: 'meter_installation_place', label: 'Место ПУ' },
				{ key: 'violations', label: 'Составлен акт БУ', edit: 'checkbox' }
			]
		},
		{
			title: 'Исполнение',
			fields: [
				{ key: 'executor', label: 'Исполнитель', edit: 'executor' },
				{ key: 'task_report', label: 'Вид работ', edit: 'work' },
				{ key: 'done_day', label: 'Дата', edit: 'date' },
				{ key: 'co_executor', label: 'Соисполнитель', edit: 'co' }
			]
		}
	];

	const query = createQuery<{ rows: UlrExecutionRow[] }>(
		toStore(() => ({
			queryKey: ['ulr-execution'],
			queryFn: () => fetchUlrExecution()
		}))
	);
	const result = fromStore(query);
	const rows = $derived(result.current.data?.rows ?? []);
	const loading = $derived(result.current.isPending);

	const today = (() => {
		const d = new Date();
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	})();

	let expanded = $state<Set<string>>(new Set());
	let selected = $state<Set<string>>(new Set());

	const allSelected = $derived(rows.length > 0 && rows.every((r) => selected.has(r.task_number ?? '')));

	function toggleExpanded(id: string) {
		const next = new Set(expanded);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		expanded = next;
	}

	function toggleSelected(id: string) {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
	}

	function toggleAll() {
		if (allSelected) selected = new Set();
		else selected = new Set(rows.map((r) => r.task_number ?? '').filter(Boolean));
	}

	const isLocked = (row: UlrExecutionRow) => !!row.reestr_number;

	async function save(
		row: UlrExecutionRow,
		patch: Partial<Pick<UlrExecutionRow, 'executor' | 'co_executor' | 'task_report' | 'done_day' | 'violations'>>
	) {
		try {
			await updateUlrExecution({
				task_number: row.task_number ?? '',
				executor: patch.executor !== undefined ? patch.executor : row.executor,
				co_executor: patch.co_executor !== undefined ? patch.co_executor : row.co_executor,
				task_report: patch.task_report !== undefined ? patch.task_report : row.task_report,
				done_day: patch.done_day !== undefined ? patch.done_day : row.done_day,
				violations: patch.violations !== undefined ? patch.violations : row.violations
			});
			await queryClient.invalidateQueries({ queryKey: ['ulr-execution'] });
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка сохранения');
		}
	}
</script>

<div class="h-full overflow-auto p-4">
	<div class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border bg-card">
		<Table containerClass="min-h-0 flex-1 overflow-auto">
			<TableHeader>
				<TableRow class="hover:bg-transparent">
					<TableHead class="sticky top-0 z-10 w-8 bg-muted text-center">
						<input type="checkbox" class="size-4 cursor-pointer accent-primary" checked={allSelected} onchange={toggleAll} />
					</TableHead>
					{#each COLUMNS as col (col.key)}
						{@const Icon = HEADER_ICONS[col.key]}
						<TableHead class="sticky top-0 z-10 bg-muted text-center">
							{#if Icon}
								<span class="inline-flex items-center justify-center" title={col.header}><Icon class="size-4" /></span>
							{:else}
								{col.header}
							{/if}
						</TableHead>
					{/each}
				</TableRow>
			</TableHeader>
			<TableBody>
				{#if loading}
					{#each Array(6) as _}
						<TableRow>
							<TableCell><Skeleton class="h-4 w-4" /></TableCell>
							{#each COLUMNS as _}
								<TableCell><Skeleton class="h-4 w-full" /></TableCell>
							{/each}
						</TableRow>
					{/each}
				{:else if rows.length === 0}
					<TableRow>
						<TableCell colspan={COLUMNS.length + 1} class="h-24 text-center text-muted-foreground">
							Нет данных
						</TableCell>
					</TableRow>
				{:else}
					{#each rows as row (row.task_number)}
						{@const id = row.task_number ?? ''}
						<TableRow
							class="cursor-pointer"
							title="ПКМ — скопировать номер задания"
							onclick={() => toggleExpanded(id)}
							oncontextmenu={(e) => {
								e.preventDefault();
								copyText(id);
							}}
						>
							<TableCell class="w-8 text-center" onclick={(e) => e.stopPropagation()}>
								<input type="checkbox" class="size-4 cursor-pointer accent-primary" checked={selected.has(id)} onchange={() => toggleSelected(id)} />
							</TableCell>
							{#each COLUMNS as col (col.key)}
								<TableCell class={col.key === 'norm' ? 'whitespace-nowrap text-center text-sm' : 'whitespace-nowrap text-sm'}>
									{#if col.key === 'reestr_number'}
										{#if row.reestr_number}
											<span class="font-bold text-brand-brown">Р</span>
										{:else}
											-
										{/if}
									{:else}
										{row[col.key] ?? ''}
									{/if}
								</TableCell>
							{/each}
						</TableRow>
						{#if expanded.has(id)}
							<TableRow class="bg-muted hover:bg-muted">
								<TableCell colspan={COLUMNS.length + 1}>
									<div class="grid grid-cols-1 gap-x-6 gap-y-4 py-2 sm:grid-cols-2 lg:grid-cols-4">
										{#each GROUPS as group (group.title)}
											<div class="space-y-2">
												{#each group.fields as f (f.key)}
													<div class="text-sm">
														{#if f.edit === 'checkbox'}
															<label class="flex items-center gap-1.5">
																<input type="checkbox" class="size-4 cursor-pointer accent-primary" checked={row.violations === 'Да'} disabled={isLocked(row)} onchange={(e) => save(row, { violations: (e.currentTarget as HTMLInputElement).checked ? 'Да' : 'Нет' })} />
																<span class="text-muted-foreground">{f.label}</span>
															</label>
														{:else if f.edit === 'executor'}
															<span class="text-muted-foreground">{f.label}:</span>{' '}
															<select class="h-8 min-w-44 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring" disabled={isLocked(row)} value={row.executor ?? ''} onchange={(e) => save(row, { executor: (e.currentTarget as HTMLSelectElement).value || null })}>
																<option value="">—</option>
																{#each row.executor_options ?? [] as n (n)}
																	<option value={n}>{n}</option>
																{/each}
															</select>
														{:else if f.edit === 'work'}
															<span class="text-muted-foreground">{f.label}:</span>{' '}
															<select class="h-8 min-w-44 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring" disabled={isLocked(row)} value={row.task_report ?? ''} onchange={(e) => save(row, { task_report: (e.currentTarget as HTMLSelectElement).value || null })}>
																<option value="">—</option>
																{#each row.work_type_options ?? [] as o (o.short)}
																	<option value={o.short ?? ''}>{o.short}</option>
																{/each}
															</select>
														{:else if f.edit === 'date'}
															<span class="text-muted-foreground">{f.label}:</span>{' '}
															<input type="date" max={today} class="h-8 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring" value={row.done_day ?? ''} disabled={isLocked(row) || row.task_report === 'Без исполнения'} onchange={(e) => save(row, { done_day: (e.currentTarget as HTMLInputElement).value || null })} />
														{:else if f.edit === 'co'}
															{#if row.co_executor_required}
																<span class="text-muted-foreground">{f.label}:</span>{' '}
																<select class="h-8 min-w-44 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring" disabled={isLocked(row)} value={row.co_executor ?? ''} onchange={(e) => save(row, { co_executor: (e.currentTarget as HTMLSelectElement).value || null })}>
																	<option value="">—</option>
																	{#each (row.executor_options ?? []).filter((n) => n !== row.executor) as n (n)}
																		<option value={n}>{n}</option>
																	{/each}
																</select>
															{/if}
														{:else}
															<span class="text-muted-foreground">{f.label}:</span>{' '}
															<span>{row[f.key] || '-'}</span>
														{/if}
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
</div>
