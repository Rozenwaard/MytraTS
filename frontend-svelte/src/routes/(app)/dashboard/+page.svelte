<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import {
		fetchDashboardOverview,
		fetchErrorsByLocale,
		fetchPriorities,
		fetchDebtMonth,
		type DashboardOverview,
		type DebtMonth,
		type ErrorsByLocale,
		type Priorities
	} from '$lib/api/dashboard';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Button } from '$lib/components/ui/button';
	import StatCard from '$lib/components/stat-card.svelte';
	import { cn } from '$lib/utils.js';
	import { auth } from '$lib/store/auth.svelte';
	import ClipboardList from '@lucide/svelte/icons/clipboard-list';
	import Wallet from '@lucide/svelte/icons/wallet';
	import CircleDollarSign from '@lucide/svelte/icons/circle-dollar-sign';
	import Users from '@lucide/svelte/icons/users';
	import Wrench from '@lucide/svelte/icons/wrench';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import ListOrdered from '@lucide/svelte/icons/list-ordered';
	import ListTodo from '@lucide/svelte/icons/list-todo';
	import ShieldAlert from '@lucide/svelte/icons/shield-alert';
	import Copy from '@lucide/svelte/icons/copy';
	import X from '@lucide/svelte/icons/x';
	import Ticket from '@lucide/svelte/icons/ticket';

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
	const workers = $derived(overview?.workers ?? { total: 0 });
	const newUsers = $derived(overview?.new_users ?? { review: 0 });
	const instrumental = $derived(overview?.instrumental ?? { ordered: 0, completed: 0 });
	const nedopuski = $derived(overview?.nedopuski ?? []);
	const tickets = $derived(overview?.tickets ?? { unanswered: 0 });

	const fmt = (n: number | undefined) => (n ?? 0).toLocaleString('ru-RU');
	const fmtMoney = (n: number | undefined) =>
		(n ?? 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	const fmtPercent = (n: number | null | undefined) =>
		n == null
			? '—'
			: `${n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;

	const prioritiesQuery = createQuery<Priorities>(
		toStore(() => ({
			queryKey: ['dashboard-priorities'],
			queryFn: () => fetchPriorities()
		}))
	);
	const prioritiesResult = fromStore(prioritiesQuery);
	const priorities = $derived(prioritiesResult.current.data?.priorities ?? []);

	const isAdmin = $derived(auth.user?.role === 'администратор');

	function errorGridClass(n: number): string {
		if (n <= 1) return 'grid-cols-1';
		if (n <= 4) return 'grid-cols-2';
		return 'grid-flow-col grid-rows-3';
	}

	let debtMonthOpen = $state(false);
	let debtMonthLoading = $state(false);
	let debtMonthError = $state<string | null>(null);
	let debtMonth = $state<DebtMonth | null>(null);

	async function openDebtMonth() {
		debtMonthOpen = true;
		debtMonthLoading = true;
		debtMonthError = null;
		try {
			debtMonth = await fetchDebtMonth();
		} catch {
			debtMonth = null;
			debtMonthError = 'Не удалось загрузить данные';
		} finally {
			debtMonthLoading = false;
		}
	}

	function closeDebtMonth() {
		debtMonthOpen = false;
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
				href={isAdmin ? '/dashboard/priorities' : undefined}
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
				title="Недопуски"
				icon={ShieldAlert}
				iconClass="bg-red-100 text-red-800"
			>
				{#snippet children()}
					<div class={cn('grid gap-2', errorGridClass(nedopuski.length))}>
						{#each nedopuski as item (item.id)}
							{@render StatRow(item.label, fmtPercent(item.percent))}
						{/each}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Заданий в работе"
				icon={ClipboardList}
				iconClass="bg-primary/10 text-primary"
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
				downloadHref={isAdmin ? '/api/dashboard/duplicates-report' : undefined}
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
				href="/admin/quarantine"
				preHref={isAdmin ? '/help/questions' : undefined}
				preIcon={Ticket}
				preLabel="Тикеты"
			>
				{#snippet children()}
					<div class="space-y-2">
						{@render StatRow('Линейные работники', fmt(workers.total))}
						{@render StatRow('Новые пользователи', fmt(newUsers.review))}
						{@render StatRow('Тикеты', fmt(tickets.unanswered))}
					</div>
				{/snippet}
			</StatCard>

			<StatCard
				title="Крупная задолженность"
				icon={CircleDollarSign}
				iconClass="bg-amber-100 text-amber-800"
				downloadHref="/api/dashboard/debt-report"
				downloadLabel="Задания"
				downloadIcon={ListTodo}
				onMonth={isAdmin ? openDebtMonth : undefined}
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

{#if debtMonthOpen}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
		role="button"
		tabindex="-1"
		aria-label="Закрыть"
		onclick={(e) => {
			if (e.target === e.currentTarget) closeDebtMonth();
		}}
		onkeydown={(e) => {
			if (e.key === 'Escape') closeDebtMonth();
		}}
	>
		<div class="w-full max-w-sm rounded-lg border bg-card p-4 shadow-lg" role="dialog" aria-modal="true">
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-base font-semibold">Крупная задолженность</h3>
				<Button variant="ghost" size="icon-sm" onclick={closeDebtMonth} aria-label="Закрыть">
					<X class="size-4" />
				</Button>
			</div>

			<div class="space-y-2 text-sm">
				<div class="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2">
					<span class="text-muted-foreground">Период</span>
					<span class="font-semibold tabular-nums">{debtMonth?.period ?? '—'}</span>
				</div>
				<div class="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2">
					<span class="text-muted-foreground">Поступило</span>
					<span class="font-semibold tabular-nums">{fmt(debtMonth?.received)}</span>
				</div>
				<div class="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2">
					<span class="text-muted-foreground">Выполнено</span>
					<span class="font-semibold tabular-nums">{fmt(debtMonth?.completed)}</span>
				</div>
				<div class="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2">
					<span class="text-muted-foreground">В срок</span>
					<span class="font-semibold tabular-nums">{fmt(debtMonth?.on_time)}</span>
				</div>
			</div>

			{#if debtMonthLoading}
				<p class="mt-3 text-center text-xs text-muted-foreground">Загрузка…</p>
			{:else if debtMonthError}
				<p class="mt-3 text-center text-xs text-destructive">{debtMonthError}</p>
			{/if}
		</div>
	</div>
{/if}

