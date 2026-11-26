<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { queryClient } from '$lib/query';
	import { fetchMytragoWorkers, enrollCode, type MytragoWorker } from '$lib/api/rks';
	import { toast } from '$lib/store/toast.svelte';
	import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '$lib/components/ui/table';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import X from '@lucide/svelte/icons/x';
	import QRCode from 'qrcode';

	const query = createQuery<{ workers: MytragoWorker[] }>(
		toStore(() => ({
			queryKey: ['mytrago-workers'],
			queryFn: () => fetchMytragoWorkers()
		}))
	);
	const result = fromStore(query);
	const workers = $derived(result.current.data?.workers ?? []);
	const loading = $derived(result.current.isPending);

	let enroll = $state<{ code: string; expires_at: string; full_name: string; qr: string; url: string } | null>(null);
	let issuing = $state<number | null>(null);

	async function issueCode(w: MytragoWorker) {
		issuing = w.id;
		try {
			const res = await enrollCode(w.id);
			const url = `${window.location.origin}/m/enroll?code=${res.code}`;
			const qr = await QRCode.toDataURL(url, { width: 240, margin: 1 });
			enroll = { ...res, qr, url };
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка генерации кода');
		} finally {
			issuing = null;
		}
	}

	function closeEnroll() {
		enroll = null;
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

{#if enroll}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
		role="button"
		tabindex="-1"
		aria-label="Закрыть"
		onclick={(e) => {
			if (e.target === e.currentTarget) closeEnroll();
		}}
		onkeydown={(e) => {
			if (e.key === 'Escape') closeEnroll();
		}}
	>
		<div class="w-full max-w-sm rounded-lg border bg-card p-4 shadow-lg" role="dialog" aria-modal="true">
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-base font-semibold">Код привязки</h3>
				<Button variant="ghost" size="icon-sm" onclick={closeEnroll} aria-label="Закрыть">
					<X class="size-4" />
				</Button>
			</div>
			<p class="text-sm text-muted-foreground">{enroll.full_name}</p>
			<div class="mt-3 flex flex-col items-center gap-3">
				{#if enroll.qr}
					<img src={enroll.qr} alt="QR-код" class="size-60 rounded-md border bg-white p-2" />
				{/if}
				<div class="rounded bg-muted px-4 py-2 text-center font-mono text-2xl tracking-widest">{enroll.code}</div>
				<p class="text-center text-xs text-muted-foreground">
					Действует до {enroll.expires_at?.slice(11, 16) ?? '—'}. Отсканируйте камерой телефона — откроется ссылка, устройство привяжется автоматически.
				</p>
			</div>
			<div class="mt-4 flex justify-end">
				<Button onclick={closeEnroll}>Закрыть</Button>
			</div>
		</div>
	</div>
{/if}
