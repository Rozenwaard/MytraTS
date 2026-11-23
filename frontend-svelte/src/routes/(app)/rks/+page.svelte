<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { toast } from '$lib/store/toast.svelte';
	import { fetchRksConsumers, type RksConsumer } from '$lib/api/rks';

	let consumers = $state<RksConsumer[]>([]);
	let total = $state(0);
	let loading = $state(true);

	onMount(async () => {
		try {
			const res = await fetchRksConsumers(5000, 0);
			consumers = res.items;
			total = res.total;
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка загрузки');
		} finally {
			loading = false;
		}
	});
</script>

<div class="h-full overflow-auto p-4">
	<div class="mx-auto max-w-5xl">
		<Card>
			<CardHeader>
				<CardTitle>Потребители РКС</CardTitle>
				<CardDescription>Всего: {total}</CardDescription>
			</CardHeader>
			<CardContent>
				{#if loading}
					<p class="text-sm text-muted-foreground">Загрузка…</p>
				{:else}
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b text-left text-muted-foreground">
								<th class="py-2 pr-2">#</th>
								<th class="py-2 pr-2">Договор</th>
								<th class="py-2 pr-2">ФЛ/ЮЛ</th>
								<th class="py-2 pr-2">Отделение</th>
								<th class="py-2 pr-2">Наименование</th>
								<th class="py-2 pr-2">Телефон</th>
								<th class="py-2">Точек</th>
							</tr>
						</thead>
						<tbody>
							{#each consumers as c (c.id)}
								<tr class="border-b">
									<td class="py-1.5 pr-2">{c.id}</td>
									<td class="py-1.5 pr-2">{c.contract_number ?? '—'}</td>
									<td class="py-1.5 pr-2">{c.fl_yul ?? '—'}</td>
									<td class="py-1.5 pr-2">{c.department ?? '—'}</td>
									<td class="py-1.5 pr-2">{c.consumer_name ?? '—'}</td>
									<td class="py-1.5 pr-2">{c.phone ?? '—'}</td>
									<td class="py-1.5">{c.points_count}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</CardContent>
		</Card>
	</div>
</div>
