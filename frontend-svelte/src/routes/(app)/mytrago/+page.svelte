<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { queryClient } from '$lib/query';
	import { fetchMytragoWorkers, enrollCode, type MytragoWorker } from '$lib/api/rks';
	import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '$lib/components/ui/table';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';

	const query = createQuery<{ workers: MytragoWorker[] }>(
		toStore(() => ({
			queryKey: ['mytrago-workers'],
			queryFn: () => fetchMytragoWorkers()
		}))
	);
	const result = fromStore(query);
	const workers = $derived(result.current.data?.workers ?? []);
	const loading = $derived(result.current.isPending);

	let enroll = $state<{ code: string; expires_at: string; full_name: string } | null>(null);
	let issuing = $state<number | null>(null);

	async function issueCode(w: MytragoWorker) {
		issuing = w.id;
		try {
			const res = await enrollCode(w.id);
			enroll = { code: res.code, expires_at: res.expires_at, full_name: w.full_name };
		} finally {
			issuing = null;
		}
	}
</script>

<div class="h-full overflow-auto p-4">
	<div class="mx-auto max-w-4xl space-y-4">
		<Card>
			<CardHeader>
				<CardTitle>MytraGo</CardTitle>
				<CardDescription>Приложение для полевых работ: скачайте APK и привяжите устройство по коду.</CardDescription>
			</CardHeader>
			<CardContent class="flex flex-wrap items-center gap-4">
				<a href="/mytrago.apk" download>
					<Button>Скачать APK</Button>
				</a>
				{#if enroll}
					<div class="rounded-md border bg-muted px-4 py-2">
						<div class="text-xs text-muted-foreground">Код для {enroll.full_name}</div>
						<div class="font-mono text-2xl tracking-widest">{enroll.code}</div>
						<div class="text-xs text-muted-foreground">Действителен до {enroll.expires_at}</div>
					</div>
				{/if}
			</CardContent>
		</Card>

		<Card>
			<CardHeader>
				<CardTitle>Работники {workers[0]?.dept ?? ''}</CardTitle>
				<CardDescription>Выдайте код привязки устройства сотруднику.</CardDescription>
			</CardHeader>
			<CardContent>
				{#if loading}
					<p class="text-sm text-muted-foreground">Загрузка…</p>
				{:else}
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>ФИО</TableHead>
								<TableHead>Таб. №</TableHead>
								<TableHead>Должность</TableHead>
								<TableHead>Отделение</TableHead>
								<TableHead>Офис</TableHead>
								<TableHead class="text-right"></TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each workers as w (w.id)}
								<TableRow>
									<TableCell class="font-medium">{w.full_name}</TableCell>
									<TableCell>{w.staff_id}</TableCell>
									<TableCell>{w.position}</TableCell>
									<TableCell>{w.dept}</TableCell>
									<TableCell>{w.locale ?? '—'}</TableCell>
									<TableCell class="text-right">
										<Button size="sm" disabled={issuing === w.id} onclick={() => issueCode(w)}>
											{issuing === w.id ? '…' : 'Выдать код'}
										</Button>
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				{/if}
			</CardContent>
		</Card>
	</div>
</div>
