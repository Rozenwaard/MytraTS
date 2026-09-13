<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import {
		fetchDashboardOverview,
		fetchErrorsByLocale,
		fetchStatus,
		type DashboardOverview,
		type ErrorsByLocale,
		type StatusState
	} from '$lib/api/dashboard';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import StatCard from '$lib/components/stat-card.svelte';
	import { cn } from '$lib/utils.js';
	import ClipboardList from '@lucide/svelte/icons/clipboard-list';
	import Wallet from '@lucide/svelte/icons/wallet';
	import CircleDollarSign from '@lucide/svelte/icons/circle-dollar-sign';
	import Users from '@lucide/svelte/icons/users';
	import Wrench from '@lucide/svelte/icons/wrench';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import ListOrdered from '@lucide/svelte/icons/list-ordered';
	import Activity from '@lucide/svelte/icons/activity';
	import Copy from '@lucide/svelte/icons/copy';

	const overviewQuery = createQuery<DashboardOverview>(
		toStore(() => ({
			queryKey: ['dashboard-overview'],
			queryFn: () => fetchDashboardOverview()
		}))
	);
	const overviewResult = fromStore(overviewQuery);
	const overview = $derived(overviewResult.current.data);
	const overviewPending = $derived(overviewResult.current.isPending);

	const errorsQuery = createQuery<ErrorsByLocale>(
		toStore(() => ({
			queryKey: ['dashboard-errors-by-locale'],
			queryFn: () => fetchErrorsByLocale()
		}))
	);
	const errorsResult = fromStore(errorsQuery);
	const errors = $derived(errorsResult.current.data);

	const statusQuery = createQuery<StatusState>(
		toStore(() => ({
			queryKey: ['status'],
			queryFn: () => fetchStatus()
		}))
	);
	const statusResult = fromStore(statusQuery);
	const status = $derived(statusResult.current.data);

	const debt = $derived(
		overview?.debt ?? {
			total: 0,
			ontime_in_work: 0,
			ontime_completed: 0,
			overdue_in_work: 0,
			overdue_completed: 0
		}
	);
	const inWorkMatrix = $derived(
		overview?.in_work_matrix ?? {
			psk_plan: 0,
			psk_unplan: 0,
			rle_plan: 0,
			rle_unplan: 0
		}
	);
	const workers = $derived(overview?.workers ?? { total: 0, controllers: 0, engineers: 0 });
	const instrumental = $derived(overview?.instrumental ?? { ordered: 0, completed: 0 });

	const fmt = (n: number | undefined) => (n ?? 0).toLocaleString('ru-RU');
	const fmtMoney = (n: number | undefined) =>
		(n ?? 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

	const priorities = ['Внеплан ПСК', 'Внеплан РЛЭ', 'Инструменталки', 'План задвигаем'];

	function errorGridClass(n: number): string {
		if (n <= 1) return 'grid-cols-1';
		if (n <= 4) return 'grid-cols-2';
		return 'grid-flow-col grid-rows-3';
	}

	function statusValue(count: string | null | undefined, at: string | null | undefined): string {
		if (!at) return '—';
		return `${count ?? '—'} · ${at}`;
	}
</script>

<div class="flex h-full flex-col gap-4 overflow-auto p-4">
	{#if overviewPending}
		<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
			{#each Array(9) as _}
				<Skeleton class="h-[220px] w-full" />
			{/each}
		</div>
	{:else if overview}
		<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
			<StatCard
				title="Приоритеты"
				icon={ListOrdered}
				iconClass="bg-orange-100 text-orange-800"
				href="/dashboard/tasks"
			>
				{#snippet children()}
					<div class={cn('grid gap-2', errorGridClass(priorities.length))}>
						{#each priorities as name, i (name)}
							{@render StatRow(`${i + 1}. ${name}`, '')}
						{/each}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Стоимость"
				icon={Wallet}
				iconClass="bg-brand-logo/10 text-brand-logo"
				href="/reports"
			>
				{#snippet children()}
					<div class="space-y-2">
						{@render StatRow('Итого', `${fmtMoney(overview.cost)} ₽`, true)}
						{@render StatRow('ПСК', `${fmtMoney(overview.cost_psk)} ₽`)}
						{@render StatRow('РЛЭ', `${fmtMoney(overview.cost_rle)} ₽`)}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Состояние"
				icon={Activity}
				iconClass="bg-emerald-100 text-emerald-800"
				href="/upload"
			>
				{#snippet children()}
					<div class="space-y-2">
						{@render StatRow('Задания в работе', statusValue(status?.in_work_count, status?.in_work_at), true)}
						{@render StatRow('Новые задания', statusValue(status?.new_tasks_count, status?.new_tasks_at))}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Заданий в работе"
				icon={ClipboardList}
				iconClass="bg-primary/10 text-primary"
				href="/dashboard/tasks"
			>
				{#snippet children()}
					<div class="grid grid-cols-[auto_1fr_1fr] gap-2 text-sm">
						<div></div>
						<div class="text-center text-xs font-medium text-muted-foreground">План</div>
						<div class="text-center text-xs font-medium text-muted-foreground">Внеплан</div>

						<div class="flex items-center text-muted-foreground">ПСК</div>
						{@render MatrixCell(inWorkMatrix.psk_plan)}
						{@render MatrixCell(inWorkMatrix.psk_unplan)}

						<div class="flex items-center text-muted-foreground">РЛЭ</div>
						{@render MatrixCell(inWorkMatrix.rle_plan)}
						{@render MatrixCell(inWorkMatrix.rle_unplan)}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Ошибки"
				icon={TriangleAlert}
				iconClass="bg-destructive/10 text-destructive"
				href="/dashboard/errors"
			>
				{#snippet children()}
					<div class={cn('grid gap-2', errorGridClass((errors?.by_locale ?? []).length))}>
						{#each errors?.by_locale ?? [] as item (item.locale)}
							{@render StatRow(item.locale, fmt(item.count))}
						{/each}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Дубли"
				icon={Copy}
				iconClass="bg-slate-100 text-slate-800"
				href="/reports/duplicates"
			>
				{#snippet children()}
					<div class="space-y-2">
						{@render StatRow('Только CRM', fmt(overview.duplicates.crm))}
						{@render StatRow('Смешанные', fmt(overview.duplicates.mixed))}
						{@render StatRow('Не CRM', fmt(overview.duplicates.non_crm))}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Активные работники"
				icon={Users}
				iconClass="bg-blue-100 text-blue-800"
				href="/dashboard/workers"
			>
				{#snippet children()}
					<div class="space-y-2">
						{@render StatRow('Всего', fmt(workers.total), true)}
						{@render StatRow('Контролёры', fmt(workers.controllers))}
						{@render StatRow('Инженеры', fmt(workers.engineers))}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Крупная задолженность"
				icon={CircleDollarSign}
				iconClass="bg-amber-100 text-amber-800"
				href="/dashboard/projects"
			>
				{#snippet children()}
					<div class="grid grid-cols-[auto_1fr_1fr] gap-2 text-sm">
						<div></div>
						<div class="text-center text-xs font-medium text-muted-foreground">Просрочено</div>
						<div class="text-center text-xs font-medium text-muted-foreground">Вовремя</div>

						<div class="flex items-center text-muted-foreground">В работе</div>
						{@render MatrixCell(debt.overdue_in_work)}
						{@render MatrixCell(debt.ontime_in_work)}

						<div class="flex items-center text-muted-foreground">Выполнено</div>
						{@render MatrixCell(debt.overdue_completed)}
						{@render MatrixCell(debt.ontime_completed)}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Инструментальные проверки"
				icon={Wrench}
				iconClass="bg-violet-100 text-violet-800"
				href="/dashboard/projects"
			>
				{#snippet children()}
					<div class="space-y-2">
						{@render StatRow('Заказано', fmt(instrumental.ordered))}
						{@render StatRow('Выполнено', fmt(instrumental.completed))}
					</div>
				{/snippet}
			</StatCard>
		</div>
	{/if}
</div>

{#snippet StatRow(label: string, value: string, emphasize = false)}
	<div
		class={cn(
			'flex items-center justify-between rounded-md border px-3 py-2',
			emphasize ? 'bg-muted/60' : 'bg-muted/40'
		)}
	>
		<span
			class={cn('text-sm', emphasize ? 'font-medium text-foreground' : 'text-muted-foreground')}
		>
			{label}
		</span>
		<span class="text-sm font-semibold tabular-nums">{value}</span>
	</div>
{/snippet}

{#snippet MatrixCell(n: number)}
	<div
		class="flex items-center justify-center rounded-md border bg-muted/40 px-2 py-2 text-sm font-semibold tabular-nums"
	>
		{fmt(n)}
	</div>
{/snippet}
