<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { fetchUlrExecution, type UlrExecutionRow } from '$lib/api/ulr';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Skeleton } from '$lib/components/ui/skeleton';

	const COLUMNS: { key: keyof UlrExecutionRow; header: string }[] = [
		{ key: 'customer', header: 'Заказчик' },
		{ key: 'work_type_in_task', header: 'Поручение' },
		{ key: 'personal_account', header: 'Точка учёта' },
		{ key: 'address', header: 'Адрес' },
		{ key: 'executor', header: 'Исполнитель' },
		{ key: 'co_executor', header: 'Соисполнитель' },
		{ key: 'task_report', header: 'Вид работ' },
		{ key: 'done_day', header: 'Дата' },
		{ key: 'reestr_number', header: 'Реестр' },
		{ key: 'errors', header: 'Ошибки' },
		{ key: 'norm', header: 'Норматив' },
		{ key: 'acts', header: 'Акт' }
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
</script>

<div class="h-full overflow-auto p-4">
	<div class="rounded-md border">
		<Table>
			<TableHeader>
				<TableRow>
					{#each COLUMNS as c (c.key)}
						<TableHead>{c.header}</TableHead>
					{/each}
				</TableRow>
			</TableHeader>
			<TableBody>
				{#if loading}
					{#each Array(6) as _}
						<TableRow>
							{#each COLUMNS as _}
								<TableCell><Skeleton class="h-5 w-full" /></TableCell>
							{/each}
						</TableRow>
					{/each}
				{:else if rows.length === 0}
					<TableRow>
						<TableCell colspan={COLUMNS.length} class="h-24 text-center text-muted-foreground">
							Нет данных
						</TableCell>
					</TableRow>
				{:else}
					{#each rows as r (r.task_number)}
						<TableRow>
							{#each COLUMNS as c (c.key)}
								<TableCell class="whitespace-nowrap text-sm">{r[c.key] ?? ''}</TableCell>
							{/each}
						</TableRow>
					{/each}
				{/if}
			</TableBody>
		</Table>
	</div>
</div>
