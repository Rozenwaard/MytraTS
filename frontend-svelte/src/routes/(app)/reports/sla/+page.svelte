<script lang="ts">
	import { fetchSla, slaDownloadUrl, type SlaResult } from '$lib/api/sla';
	import { auth } from '$lib/store/auth.svelte';
	import { toast } from '$lib/store/toast.svelte';
	import { Button } from '$lib/components/ui/button';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Skeleton } from '$lib/components/ui/skeleton';

	const isAdmin = $derived(
		auth.user?.role === 'администратор' || auth.user?.role === 'специалист'
	);

	let data = $state<SlaResult | null>(null);
	let month = $state('');
	let loading = $state(true);
	let started = $state(false);

	async function load(m: string) {
		loading = true;
		try {
			const d = await fetchSla(m || undefined);
			data = d;
			month = d.month;
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка загрузки СЛА');
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (isAdmin && !started) {
			started = true;
			load('');
		}
	});

	function num(v: number): string {
		return v.toLocaleString('ru-RU');
	}
	function money(v: number): string {
		return v.toLocaleString('ru-RU', {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2
		});
	}
	function coef(v: number): string {
		return v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
	}
	function pct(v: number): string {
		return (
			v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%'
		);
	}
</script>

{#if auth.loading}
	<div class="p-6"><Skeleton class="h-6 w-40" /></div>
{:else if !isAdmin}
	<div class="p-6 text-sm text-muted-foreground">Нет доступа</div>
{:else}
	<div class="flex h-full flex-col gap-3 overflow-auto p-3">
		<div class="flex items-center gap-3">
			<h2 class="text-lg font-semibold">СЛА — полнота (ПСК)</h2>
			<input
				type="month"
				value={month}
				disabled={loading}
				onchange={(e) => load((e.currentTarget as HTMLInputElement).value)}
				class="h-8 rounded-md border border-input bg-background px-2 text-sm"
			/>
			<Button
				size="sm"
				variant="outline"
				disabled={loading || !data}
				onclick={() => window.open(slaDownloadUrl(month), '_blank')}
			>
				Скачать
			</Button>
		</div>

		{#if loading && !data}
			<div class="space-y-2">
				{#each Array(3) as _}
					<Skeleton class="h-8 w-full" />
				{/each}
			</div>
		{:else if data}
			<div class="overflow-x-auto rounded-md border">
				<Table>
					<TableHeader>
						<TableRow class="hover:bg-transparent">
							<TableHead class="whitespace-nowrap text-center">Код</TableHead>
							<TableHead class="whitespace-nowrap text-left">Работа</TableHead>
							<TableHead class="whitespace-nowrap text-right">Заказ</TableHead>
							<TableHead class="whitespace-nowrap text-right">Выполнение</TableHead>
							<TableHead class="whitespace-nowrap text-right">Домов</TableHead>
							<TableHead class="whitespace-nowrap text-right">Нерез. %</TableHead>
							<TableHead class="whitespace-nowrap text-right">Общий к-т</TableHead>
							<TableHead class="whitespace-nowrap text-right">Ступень</TableHead>
							<TableHead class="whitespace-nowrap text-right">Расценка (база)</TableHead>
							<TableHead class="whitespace-nowrap text-right">Расценка (СЛА)</TableHead>
							<TableHead class="whitespace-nowrap text-right">Сумма СЛА</TableHead>
							<TableHead class="whitespace-nowrap text-right">Потери, руб</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each data.rows as row (row.code)}
							<TableRow class="hover:bg-transparent">
								<TableCell class="whitespace-nowrap text-center">{row.code}</TableCell>
								<TableCell class="whitespace-nowrap text-left">{row.task_report}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{num(row.quantity)}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{num(row.resultative)}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{num(row.houses)}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{pct(row.non_resultative_pct)}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{coef(row.smooth_coef)}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{row.sla_coef}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{money(row.rate)}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{money(row.rate_sla)}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{money(row.sum_sla)}</TableCell>
								<TableCell class="whitespace-nowrap text-right tabular-nums">{money(row.reduction)}</TableCell>
							</TableRow>
						{/each}
						<TableRow class="bg-muted/40 hover:bg-muted/40">
							<TableCell class="whitespace-nowrap font-medium" colspan={6}>Итого</TableCell>
							<TableCell class="whitespace-nowrap text-right font-medium tabular-nums" colspan={2}>—</TableCell>
							<TableCell class="whitespace-nowrap text-right font-medium tabular-nums" colspan={2}>
								{money(data.totals.base)}
							</TableCell>
							<TableCell class="whitespace-nowrap text-right font-medium tabular-nums">
								{money(data.totals.sum_sla)}
							</TableCell>
							<TableCell class="whitespace-nowrap text-right font-medium tabular-nums">
								{money(data.totals.reduction)}
							</TableCell>
						</TableRow>
					</TableBody>
				</Table>
			</div>
		{/if}
	</div>
{/if}
