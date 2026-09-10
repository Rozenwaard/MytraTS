<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import {
		fetchDashboardOverview,
		fetchErrorsByLocale,
		type DashboardOverview,
		type ErrorsByLocale
	} from '$lib/api/dashboard';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { auth } from '$lib/store/auth.svelte';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';

	const isAdmin = $derived(
		auth.user?.role === 'администратор' || auth.user?.role === 'специалист'
	);

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
			queryFn: () => fetchErrorsByLocale(),
			enabled: isAdmin
		}))
	);
	const errorsResult = fromStore(errorsQuery);
	const errors = $derived(errorsResult.current.data);

	let errorsExpanded = $state(false);

	const fmt = (n: number | undefined) => (n ?? 0).toLocaleString('ru-RU');
	const fmtMoney = (n: number | undefined) =>
		(n ?? 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
</script>

<div class="flex h-full flex-col gap-3 overflow-auto p-3">
	{#if overviewPending}
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
			{#each Array(5) as _}
				<Skeleton class="h-20 w-full" />
			{/each}
		</div>
	{:else if overview}
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
			{@render StatCard('Заданий', fmt(overview.total))}
			{@render StatCard('ПСК', fmt(overview.psk))}
			{@render StatCard('РЛЭ', fmt(overview.rle))}
			{@render StatCard('План', fmt(overview.plan))}
			{@render StatCard('Внеплан', fmt(overview.unplan))}
			{@render StatCard('Выполнено', fmt(overview.completed))}
			{@render StatCard('Не выполнено', fmt(overview.uncompleted))}
			{@render StatCard('С ошибками', fmt(overview.with_errors))}
			{@render StatCard('Без ошибок', fmt(overview.without_errors))}
			{@render StatCard('Стоимость', `${fmtMoney(overview.cost)} ₽`)}
		</div>
	{/if}

	{#if isAdmin}
		<div class="rounded-md border bg-card p-3">
			<button
				type="button"
				class="flex w-full items-center justify-between gap-2 text-left"
				onclick={() => (errorsExpanded = !errorsExpanded)}
			>
				<span class="text-sm font-medium">Отчёт об ошибках</span>
				<span class="flex items-center gap-2">
					<span class="text-xl font-semibold tabular-nums">{errors ? fmt(errors.total) : '…'}</span>
					<ChevronDown
						class={`size-4 shrink-0 text-muted-foreground transition-transform ${errorsExpanded ? 'rotate-180' : ''}`}
					/>
				</span>
			</button>

			{#if errorsExpanded}
				<div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
					{#each errors?.by_locale ?? [] as item (item.locale)}
						<div class="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2">
							<span class="text-sm text-muted-foreground">{item.locale}</span>
							<span class="text-sm font-semibold tabular-nums">{item.count}</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>

{#snippet StatCard(label: string, value: string)}
	<div class="rounded-md border bg-card p-3">
		<div class="text-xs text-muted-foreground">{label}</div>
		<div class="text-lg font-semibold tabular-nums truncate">{value}</div>
	</div>
{/snippet}
